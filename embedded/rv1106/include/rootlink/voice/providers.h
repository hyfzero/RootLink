#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>

#include "rootlink/audio/status.h"
#include "rootlink/voice/role.h"
#include "rootlink/voice/runtime_config.h"

namespace rootlink::voice {

using StopRequested = std::function<bool()>;
using TextDelta = std::function<void(const std::string&)>;

/** @brief 单次 HTTPS 请求，正文、响应上限和超时均由调用者显式约束。 */
struct HttpRequest {
  std::string method{"POST"};
  std::string url;
  std::map<std::string, std::string> headers;
  std::vector<std::uint8_t> body;
  long connect_timeout_ms{5000};
  long total_timeout_ms{45000};
  std::size_t response_limit{2U * 1024U * 1024U};
  bool stream{false};
};

/** @brief 有界响应；流式请求的正文经回调消费，不在此重复保存。 */
struct HttpResponse {
  long status_code{0};
  std::map<std::string, std::string> headers;
  std::vector<std::uint8_t> body;
};

/** @brief 仅计数的网络统计，不包含密钥、录音或云端原始响应。 */
struct HttpClientStats {
  std::uint64_t requests{0};
  std::uint64_t retries{0};
  std::uint64_t authentication_errors{0};
  std::uint64_t rate_limit_errors{0};
  std::uint64_t provider_errors{0};
};

/** @brief 可注入的 HTTP 边界；cancel 必须能打断正在进行的请求。 */
class HttpClient {
 public:
  virtual ~HttpClient() = default;
  virtual audio::Result<HttpResponse> perform(const HttpRequest& request,
                                               const StopRequested& stopped,
                                               const std::function<audio::Status(
                                                   const char*, std::size_t)>& stream_chunk = {}) = 0;
  virtual void cancel() noexcept = 0;
  virtual void noteRetry() noexcept = 0;
  virtual HttpClientStats stats() const noexcept = 0;
};

/** @brief 整句 ASR；输入为 16 kHz 单声道 PCM16，最多 30 秒。 */
class AsrProvider {
 public:
  virtual ~AsrProvider() = default;
  virtual audio::Result<std::string> transcribe(const std::vector<std::int16_t>& samples,
                                                const StopRequested& stopped) = 0;
  virtual void cancel() noexcept = 0;
};

/** @brief OpenAI messages 语义；回调仅输出可显示文本，不输出推理或执行工具。 */
class LlmProvider {
 public:
  virtual ~LlmProvider() = default;
  virtual audio::Result<std::string> complete(const std::vector<ChatMessage>& messages,
                                              const TextDelta& on_delta,
                                              const StopRequested& stopped) = 0;
  virtual void cancel() noexcept = 0;
};

/** @brief 整段合成；返回经过格式校验的 PCM，不在板端自动重采样。 */
class TtsProvider {
 public:
  virtual ~TtsProvider() = default;
  virtual audio::Result<std::vector<std::int16_t>> synthesize(
      const std::string& text, const StopRequested& stopped) = 0;
  virtual void cancel() noexcept = 0;
};

/** @brief 离线仿真供应商；不读密钥、不访问网络，返回确定性结果。 */
class MockAsrProvider final : public AsrProvider {
 public:
  audio::Result<std::string> transcribe(const std::vector<std::int16_t>&,
                                        const StopRequested& stopped) override;
  void cancel() noexcept override { cancelled_.store(true); }
 private:
  std::atomic<bool> cancelled_{false};
};

/** @brief 离线分段文本回复，用于状态机和首字耗时测试。 */
class MockLlmProvider final : public LlmProvider {
 public:
  audio::Result<std::string> complete(const std::vector<ChatMessage>& messages,
                                      const TextDelta& on_delta,
                                      const StopRequested& stopped) override;
  void cancel() noexcept override { cancelled_.store(true); }
 private:
  std::atomic<bool> cancelled_{false};
};

/** @brief 确定性测试音，不是人声；仿真播放不会访问声卡。 */
class MockTtsProvider final : public TtsProvider {
 public:
  audio::Result<std::vector<std::int16_t>> synthesize(const std::string& text,
                                                       const StopRequested& stopped) override;
  void cancel() noexcept override { cancelled_.store(true); }
 private:
  std::atomic<bool> cancelled_{false};
};

#if defined(ROOTLINK_SERVICE_API_CURL)
/** @brief 同步、可取消的 TLS 传输；同一实例不允许并发 perform。 */
class CurlHttpClient final : public HttpClient {
 public:
  CurlHttpClient();
  ~CurlHttpClient() override;
  /** @brief 不联网检查 libcurl 的 HTTPS/TLS 支持和默认 CA 文件/目录。 */
  audio::Status checkEnvironment() const;
  audio::Result<HttpResponse> perform(const HttpRequest& request,
                                      const StopRequested& stopped,
                                      const std::function<audio::Status(
                                          const char*, std::size_t)>& stream_chunk = {}) override;
  void cancel() noexcept override;
  void noteRetry() noexcept override { ++retries_; }
  HttpClientStats stats() const noexcept override;
 private:
  std::atomic<bool> cancelled_{false};
  std::atomic<std::uint64_t> requests_{0};
  std::atomic<std::uint64_t> retries_{0};
  std::atomic<std::uint64_t> authentication_errors_{0};
  std::atomic<std::uint64_t> rate_limit_errors_{0};
  std::atomic<std::uint64_t> provider_errors_{0};
};

/** @brief DashScope Qwen ASR，内存 WAV + Base64 Data URI，无公开录音上传。 */
class DashScopeAsrProvider final : public AsrProvider {
 public:
  DashScopeAsrProvider(HttpClient& http, RuntimeConfig config);
  audio::Result<std::string> transcribe(const std::vector<std::int16_t>& samples,
                                        const StopRequested& stopped) override;
  void cancel() noexcept override;
 private:
  HttpClient& http_;
  RuntimeConfig config_;
};

/** @brief 国内 OpenAI 兼容端点；解析任意分包 SSE，并去重 MiniMax 累积文本。 */
class OpenAiCompatibleLlmProvider final : public LlmProvider {
 public:
  OpenAiCompatibleLlmProvider(HttpClient& http, RuntimeConfig config);
  audio::Result<std::string> complete(const std::vector<ChatMessage>& messages,
                                      const TextDelta& on_delta,
                                      const StopRequested& stopped) override;
  void cancel() noexcept override;
 private:
  HttpClient& http_;
  RuntimeConfig config_;
};

/** @brief CosyVoice HTTP 整段合成；音频下载只允许 HTTPS 且不附带 API 密钥。 */
class DashScopeTtsProvider final : public TtsProvider {
 public:
  DashScopeTtsProvider(HttpClient& http, RuntimeConfig config);
  audio::Result<std::vector<std::int16_t>> synthesize(
      const std::string& text, const StopRequested& stopped) override;
  void cancel() noexcept override;
 private:
  HttpClient& http_;
  RuntimeConfig config_;
};
#endif

}  // namespace rootlink::voice
