#include "rootlink/voice/json_value.h"

#include <cctype>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace rootlink::voice {
namespace {

class Parser {
 public:
  explicit Parser(const std::string& input) : input_(input) {}

  JsonValue parse() {
    skipSpace();
    JsonValue result = value();
    skipSpace();
    if (position_ != input_.size()) fail("JSON 根值之后存在多余字符");
    return result;
  }

 private:
  JsonValue value() {
    if (++depth_ > 64) fail("JSON 嵌套超过 64 层");
    struct DepthGuard { std::size_t& depth; ~DepthGuard() { --depth; } } guard{depth_};
    if (position_ >= input_.size()) fail("JSON 意外结束");
    const char current = input_[position_];
    if (current == '{') return object();
    if (current == '[') return array();
    if (current == '"') return JsonValue(string());
    if (current == 't') return literal("true", JsonValue(true));
    if (current == 'f') return literal("false", JsonValue(false));
    if (current == 'n') return literal("null", JsonValue());
    if (current == '-' || std::isdigit(static_cast<unsigned char>(current))) return number();
    fail("JSON 值起始字符无效");
    return {};
  }

  JsonValue object() {
    ++position_;
    JsonValue::Object output;
    skipSpace();
    if (consume('}')) return JsonValue(std::move(output));
    while (true) {
      skipSpace();
      if (position_ >= input_.size() || input_[position_] != '"') fail("对象键必须是字符串");
      std::string key = string();
      skipSpace();
      if (!consume(':')) fail("对象键后缺少冒号");
      skipSpace();
      output[std::move(key)] = value();
      skipSpace();
      if (consume('}')) break;
      if (!consume(',')) fail("对象成员之间缺少逗号");
    }
    return JsonValue(std::move(output));
  }

  JsonValue array() {
    ++position_;
    JsonValue::Array output;
    skipSpace();
    if (consume(']')) return JsonValue(std::move(output));
    while (true) {
      skipSpace();
      output.push_back(value());
      skipSpace();
      if (consume(']')) break;
      if (!consume(',')) fail("数组元素之间缺少逗号");
    }
    return JsonValue(std::move(output));
  }

  std::string string() {
    if (!consume('"')) fail("字符串缺少起始引号");
    std::string output;
    while (position_ < input_.size()) {
      const unsigned char current = static_cast<unsigned char>(input_[position_++]);
      if (current == '"') return output;
      if (current < 0x20) fail("字符串包含控制字符");
      if (current != '\\') {
        output.push_back(static_cast<char>(current));
        continue;
      }
      if (position_ >= input_.size()) fail("字符串转义不完整");
      const char escaped = input_[position_++];
      switch (escaped) {
        case '"': output.push_back('"'); break;
        case '\\': output.push_back('\\'); break;
        case '/': output.push_back('/'); break;
        case 'b': output.push_back('\b'); break;
        case 'f': output.push_back('\f'); break;
        case 'n': output.push_back('\n'); break;
        case 'r': output.push_back('\r'); break;
        case 't': output.push_back('\t'); break;
        case 'u': appendUnicode(output); break;
        default: fail("字符串转义无效");
      }
    }
    fail("字符串缺少结束引号");
    return {};
  }

  unsigned unicodeUnit() {
    unsigned value = 0;
    for (int index = 0; index < 4; ++index) {
      if (position_ >= input_.size()) fail("Unicode 转义不完整");
      const char c = input_[position_++];
      value <<= 4U;
      if (c >= '0' && c <= '9') value |= static_cast<unsigned>(c - '0');
      else if (c >= 'a' && c <= 'f') value |= static_cast<unsigned>(c - 'a' + 10);
      else if (c >= 'A' && c <= 'F') value |= static_cast<unsigned>(c - 'A' + 10);
      else fail("Unicode 转义包含非十六进制字符");
    }
    return value;
  }

  void appendUnicode(std::string& output) {
    unsigned value = unicodeUnit();
    if (value >= 0xd800U && value <= 0xdbffU) {
      if (!consume('\\') || !consume('u')) fail("Unicode 高代理项缺少低代理项");
      const unsigned low = unicodeUnit();
      if (low < 0xdc00U || low > 0xdfffU) fail("Unicode 低代理项无效");
      value = 0x10000U + ((value - 0xd800U) << 10U) + low - 0xdc00U;
    } else if (value >= 0xdc00U && value <= 0xdfffU) fail("Unicode 孤立低代理项");
    if (value <= 0x7fU) output.push_back(static_cast<char>(value));
    else if (value <= 0x7ffU) {
      output.push_back(static_cast<char>(0xc0U | (value >> 6U)));
      output.push_back(static_cast<char>(0x80U | (value & 0x3fU)));
    } else if (value <= 0xffffU) {
      output.push_back(static_cast<char>(0xe0U | (value >> 12U)));
      output.push_back(static_cast<char>(0x80U | ((value >> 6U) & 0x3fU)));
      output.push_back(static_cast<char>(0x80U | (value & 0x3fU)));
    } else {
      output.push_back(static_cast<char>(0xf0U | (value >> 18U)));
      output.push_back(static_cast<char>(0x80U | ((value >> 12U) & 0x3fU)));
      output.push_back(static_cast<char>(0x80U | ((value >> 6U) & 0x3fU)));
      output.push_back(static_cast<char>(0x80U | (value & 0x3fU)));
    }
  }

  JsonValue number() {
    const std::size_t begin = position_;
    if (consume('-')) {}
    if (consume('0')) {
      if (position_ < input_.size() && std::isdigit(static_cast<unsigned char>(input_[position_])))
        fail("数字包含前导零");
    } else {
      if (position_ >= input_.size() || !std::isdigit(static_cast<unsigned char>(input_[position_])))
        fail("数字整数部分无效");
      while (position_ < input_.size() && std::isdigit(static_cast<unsigned char>(input_[position_]))) ++position_;
    }
    if (consume('.')) {
      if (position_ >= input_.size() || !std::isdigit(static_cast<unsigned char>(input_[position_]))) fail("小数部分无效");
      while (position_ < input_.size() && std::isdigit(static_cast<unsigned char>(input_[position_]))) ++position_;
    }
    if (position_ < input_.size() && (input_[position_] == 'e' || input_[position_] == 'E')) {
      ++position_;
      if (position_ < input_.size() && (input_[position_] == '+' || input_[position_] == '-')) ++position_;
      if (position_ >= input_.size() || !std::isdigit(static_cast<unsigned char>(input_[position_]))) fail("指数部分无效");
      while (position_ < input_.size() && std::isdigit(static_cast<unsigned char>(input_[position_]))) ++position_;
    }
    const double parsed = std::strtod(input_.substr(begin, position_ - begin).c_str(), nullptr);
    if (!std::isfinite(parsed)) fail("数字超出范围");
    return JsonValue(parsed);
  }

  JsonValue literal(const char* token, JsonValue result) {
    const std::string expected(token);
    if (input_.compare(position_, expected.size(), expected) != 0) fail("JSON 字面量无效");
    position_ += expected.size();
    return result;
  }

  bool consume(char expected) {
    if (position_ < input_.size() && input_[position_] == expected) {
      ++position_;
      return true;
    }
    return false;
  }
  void skipSpace() {
    while (position_ < input_.size() && std::isspace(static_cast<unsigned char>(input_[position_]))) ++position_;
  }
  [[noreturn]] void fail(const std::string& message) const {
    throw std::runtime_error(message + "（字节 " + std::to_string(position_) + "）");
  }

  const std::string& input_;
  std::size_t position_{0};
  std::size_t depth_{0};
};

std::string escape(const std::string& input) {
  std::ostringstream output;
  output << '"';
  for (const unsigned char c : input) {
    switch (c) {
      case '"': output << "\\\""; break;
      case '\\': output << "\\\\"; break;
      case '\b': output << "\\b"; break;
      case '\f': output << "\\f"; break;
      case '\n': output << "\\n"; break;
      case '\r': output << "\\r"; break;
      case '\t': output << "\\t"; break;
      default:
        if (c < 0x20) output << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(c);
        else output << static_cast<char>(c);
    }
  }
  output << '"';
  return output.str();
}

}  // namespace

bool JsonValue::isNull() const noexcept { return std::holds_alternative<std::nullptr_t>(value_); }
bool JsonValue::isObject() const noexcept { return std::holds_alternative<Object>(value_); }
bool JsonValue::isArray() const noexcept { return std::holds_alternative<Array>(value_); }
const JsonValue::Object& JsonValue::object() const { return std::get<Object>(value_); }
const JsonValue::Array& JsonValue::array() const { return std::get<Array>(value_); }
std::string JsonValue::stringOr(const std::string& fallback) const {
  if (const auto* value = std::get_if<std::string>(&value_)) return *value;
  return fallback;
}
double JsonValue::numberOr(double fallback) const noexcept {
  if (const auto* value = std::get_if<double>(&value_)) return *value;
  return fallback;
}
bool JsonValue::boolOr(bool fallback) const noexcept {
  if (const auto* value = std::get_if<bool>(&value_)) return *value;
  return fallback;
}
const JsonValue* JsonValue::find(const std::string& key) const noexcept {
  const auto* object_value = std::get_if<Object>(&value_);
  if (object_value == nullptr) return nullptr;
  const auto found = object_value->find(key);
  return found == object_value->end() ? nullptr : &found->second;
}

std::string JsonValue::dump() const {
  if (isNull()) return "null";
  if (const auto* value = std::get_if<bool>(&value_)) return *value ? "true" : "false";
  if (const auto* value = std::get_if<double>(&value_)) {
    std::ostringstream output;
    output << std::setprecision(15) << *value;
    return output.str();
  }
  if (const auto* value = std::get_if<std::string>(&value_)) return escape(*value);
  if (const auto* values = std::get_if<Array>(&value_)) {
    std::string output = "[";
    for (std::size_t index = 0; index < values->size(); ++index) {
      if (index != 0) output += ',';
      output += (*values)[index].dump();
    }
    return output + ']';
  }
  const auto& values = std::get<Object>(value_);
  std::string output = "{";
  bool first = true;
  for (const auto& [key, value] : values) {
    if (!first) output += ',';
    first = false;
    output += escape(key) + ':' + value.dump();
  }
  return output + '}';
}

audio::Result<JsonValue> JsonValue::parse(const std::string& input) {
  try {
    return audio::Result<JsonValue>(Parser(input).parse());
  } catch (const std::exception& error) {
    return audio::Result<JsonValue>(audio::Status(audio::AudioError::kUnsupportedFormat,
                                                  "无法解析 JSON：" + std::string(error.what())));
  }
}

}  // namespace rootlink::voice
