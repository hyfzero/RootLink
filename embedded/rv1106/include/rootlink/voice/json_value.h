#pragma once

#include <map>
#include <string>
#include <variant>
#include <vector>

#include "rootlink/audio/status.h"

namespace rootlink::voice {

/**
 * @brief 供配置和测试使用的无依赖 JSON 值。
 *
 * 云端构建仍使用 json-c 解析供应商响应；这里保留一个体积很小的严格解析器，使
 * mock 构建无需安装 json-c 也能读取 RootLink 导出的角色和 models.json。
 */
class JsonValue {
 public:
  using Object = std::map<std::string, JsonValue>;
  using Array = std::vector<JsonValue>;
  using Storage = std::variant<std::nullptr_t, bool, double, std::string, Array, Object>;

  JsonValue() = default;
  explicit JsonValue(bool value) : value_(value) {}
  explicit JsonValue(double value) : value_(value) {}
  explicit JsonValue(std::string value) : value_(std::move(value)) {}
  explicit JsonValue(Array value) : value_(std::move(value)) {}
  explicit JsonValue(Object value) : value_(std::move(value)) {}

  bool isNull() const noexcept;
  bool isObject() const noexcept;
  bool isArray() const noexcept;
  const Object& object() const;
  const Array& array() const;
  std::string stringOr(const std::string& fallback = {}) const;
  double numberOr(double fallback = 0.0) const noexcept;
  bool boolOr(bool fallback = false) const noexcept;
  const JsonValue* find(const std::string& key) const noexcept;
  std::string dump() const;

  static audio::Result<JsonValue> parse(const std::string& input);

 private:
  Storage value_{nullptr};
};

}  // namespace rootlink::voice
