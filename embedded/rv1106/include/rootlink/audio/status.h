#pragma once

#include <string>
#include <optional>
#include <utility>

namespace rootlink::audio {

/// 音频和 Stage 2 所有可预期失败的稳定分类；调用方不需要解析错误文本。
enum class AudioError {
  kOk = 0,
  kInvalidArgument,
  kInvalidState,
  kTimeout,
  kClosed,
  kDeviceError,
  kIoError,
  kUnsupportedFormat,
  kEndOfStream,
  kInterrupted,
  kConfigError,
  kNetworkError,
  kAuthenticationError,
  kRateLimited,
  kProviderError,
  kCancelled,
  kStorageError,
};

/**
 * @brief 轻量错误返回值，不抛异常、不包含音频数据。
 *
 * code 用于程序分支，message 用于日志和板端排错。默认构造即成功状态。
 */
class Status {
 public:
  Status() = default;
  Status(AudioError code, std::string message)
      : code_(code), message_(std::move(message)) {}

  static Status okStatus() { return {}; }

  bool ok() const noexcept { return code_ == AudioError::kOk; }
  AudioError code() const noexcept { return code_; }
  const std::string& message() const noexcept { return message_; }

 private:
  AudioError code_{AudioError::kOk};
  std::string message_;
};

/** @brief 值或错误二选一；必须先检查 ok()，成功后才能访问 value()。 */
template <typename T>
class Result {
 public:
  explicit Result(T value) : value_(std::move(value)) {}
  explicit Result(Status status) : status_(std::move(status)) {}

  bool ok() const noexcept { return status_.ok() && value_.has_value(); }
  const Status& status() const noexcept { return status_; }
  const T& value() const& { return *value_; }
  T& value() & { return *value_; }
  T&& value() && { return std::move(*value_); }

 private:
  Status status_{};
  std::optional<T> value_;
};

}  // namespace rootlink::audio
