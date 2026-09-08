#include <iostream>
#include <string>
#include <vector>
#include "rootlink/voice/providers.h"
#include "rootlink/voice/codec.h"
#include "rootlink/voice/json_value.h"

using namespace rootlink::voice;
using rootlink::audio::Status;
using rootlink::audio::Result;
using rootlink::audio::AudioError;
namespace {
int failures = 0;
#define CHECK(x) do { if (!(x)) { std::cerr << __LINE__ << ": " #x "\n"; ++failures; } } while (false)

// 所有请求被此边界截获；默认 CTest 永远不会访问网络，也不需要真实 API Key。
class FakeHttp final : public HttpClient {
 public:
  std::vector<HttpRequest> requests;
  std::vector<std::uint8_t> body;
  std::string stream;
  AudioError fail_first{AudioError::kOk};
  std::size_t fail_request_number{0};
  std::string fail_message{"injected"};
  bool fail_after_stream{false};
  std::size_t retries{0};
  Result<HttpResponse> perform(const HttpRequest& request, const StopRequested& stopped,
      const std::function<Status(const char*, std::size_t)>& callback) override {
    requests.push_back(request);
    if (stopped && stopped()) return Result<HttpResponse>(Status(AudioError::kCancelled, "cancelled"));
    if (requests.size() == 1 && fail_first != AudioError::kOk)
      return Result<HttpResponse>(Status(fail_first, fail_message));
    if (fail_request_number == requests.size())
      return Result<HttpResponse>(Status(AudioError::kProviderError, fail_message));
    if (callback) {
      for (const char c : stream) {
        auto status = callback(&c, 1);  // 包括中文 UTF-8 在内，按任意单字节边界拆包。
        if (!status.ok()) return Result<HttpResponse>(status);
      }
      if (fail_after_stream) return Result<HttpResponse>(Status(AudioError::kNetworkError, "broken"));
    }
    HttpResponse response;
    response.status_code = 200;
    response.body = request.method == "GET" ? pcm16ToWav({1, 2, 3}) : body;
    return Result<HttpResponse>(std::move(response));
  }
  void cancel() noexcept override {}
  void noteRetry() noexcept override { ++retries; }
  HttpClientStats stats() const noexcept override { return {}; }
  void json(const std::string& text) { body.assign(text.begin(), text.end()); }
};
RuntimeConfig config() {
  RuntimeConfig c;
  c.asr.api_key = c.llm.api_key = c.tts.api_key = "test-placeholder";
  return c;
}
void asrAndTts() {
  auto c = config();
  c.retry_count = 0;
  FakeHttp http;
  http.json(R"({"choices":[{"message":{"content":"你好"}}]})");
  DashScopeAsrProvider asr(http, c);
  auto result = asr.transcribe(std::vector<std::int16_t>(320), {});
  CHECK(result.ok() && result.value() == "你好");
  auto request = JsonValue::parse(std::string(http.requests[0].body.begin(), http.requests[0].body.end()));
  CHECK(request.ok());
  CHECK(request.value().find("model")->stringOr() == "qwen3-asr-flash");
  CHECK(request.value().dump().find("data:audio/wav;base64,UklGR") != std::string::npos);
  CHECK(!asr.transcribe(std::vector<std::int16_t>(480001), {}).ok());
  http.requests.clear();
  http.json(R"({"output":{"audio":{"url":"https://example.invalid/audio.wav"}}})");
  std::vector<std::string> diagnostics;
  DashScopeTtsProvider tts(http, c, [&](const std::string& event) { diagnostics.push_back(event); });
  auto speech = tts.synthesize("测试", {});
  CHECK(speech.ok() && speech.value().size() == 3); // 云端不足一帧必须合法。
  request = JsonValue::parse(std::string(http.requests[0].body.begin(), http.requests[0].body.end()));
  CHECK(request.ok() && request.value().find("parameters") == nullptr);
  CHECK(request.value().find("input")->find("sample_rate")->numberOr() == 16000);
  CHECK(request.value().find("input")->find("voice")->stringOr() == "longanyang");
  CHECK(http.requests[1].headers.empty()); // 下载绝不携带云端鉴权头。
  CHECK(diagnostics.size() == 2 && diagnostics[0].find("tts_cosyvoice_post_ms=") == 0 &&
        diagnostics[1].find("tts_audio_get_ms=") == 0);
  FakeHttp post_failure;
  post_failure.fail_first = AudioError::kProviderError;
  post_failure.fail_message = "HTTP 503 service unavailable";
  DashScopeTtsProvider failing_post(post_failure, c);
  const auto post_result = failing_post.synthesize("测试", {});
  CHECK(!post_result.ok() && post_result.status().message().find("CosyVoice POST 失败，耗时 ") == 0 &&
        post_result.status().message().find("HTTP 503") != std::string::npos &&
        post_result.status().message().find("错误类别=") != std::string::npos);
  FakeHttp get_failure;
  get_failure.json(R"({"output":{"audio":{"url":"https://example.invalid/audio.wav"}}})");
  get_failure.fail_request_number = 2;
  get_failure.fail_message = "HTTP 504 gateway timeout";
  DashScopeTtsProvider failing_get(get_failure, c);
  const auto get_result = failing_get.synthesize("测试", {});
  CHECK(!get_result.ok() && get_result.status().message().find("CosyVoice 音频 GET 失败，耗时 ") == 0 &&
        get_result.status().message().find("HTTP 504") != std::string::npos &&
        get_result.status().message().find("错误类别=") != std::string::npos);
  http.requests.clear();
  http.json(R"({"output":{"audio":{"url":"http://example.invalid/audio.wav"}}})");
  CHECK(!tts.synthesize("测试", {}).ok());
  CHECK(http.requests.size() == 1);
  http.requests.clear();
  http.json(R"({"output":{"audio":{"url":"http://dashscope-result.oss-cn-beijing.aliyuncs.com/a.wav?Signature=a%2Bb"}}})");
  CHECK(tts.synthesize("测试", {}).ok());
  CHECK(http.requests[1].url == "https://dashscope-result.oss-cn-beijing.aliyuncs.com/a.wav?Signature=a%2Bb");
  CHECK(http.requests[1].headers.empty());
}
void strictCloudJson() {
  FakeHttp http;
  DashScopeAsrProvider asr(http, config());
  const std::string valid = R"({"choices":[{"message":{"content":"ok"}}]})";
  for (const auto& invalid : {valid + "garbage", valid + "{}", valid + std::string(1, '\0'),
       std::string(R"({"choices":[{"message":{"content":"ok"}},]})"),
       std::string(R"({/*comment*/"choices":[{"message":{"content":"ok"}}]})")}) {
    http.json(invalid);
    CHECK(!asr.transcribe(std::vector<std::int16_t>(320), {}).ok());
  }
  http.json(valid + " \r\n\t");
  CHECK(asr.transcribe(std::vector<std::int16_t>(320), {}).ok());
  http.json(std::string(2U * 1024U * 1024U + 1U, ' '));
  CHECK(!asr.transcribe(std::vector<std::int16_t>(320), {}).ok());
}
void llmStreams() {
  auto c = config(); c.llm.name = "minimax";
  c.llm.headers["Authorization"] = "Bearer stale-placeholder";
  c.llm.headers["Content-Type"] = "text/plain";
  FakeHttp http;
  http.stream = "data: {\"choices\":[{\"delta\":{\"reasoning_content\":\"hidden\"}}]}\n\n"
      "data: {\"choices\":[{\"delta\":{\"content\":\"你\"}}]}\n\n"
      "data: {\"choices\":[{\"delta\":{\"content\":\"你好\"}}]}\n\n"
      "data: [DONE]\n\n";
  OpenAiCompatibleLlmProvider llm(http, c);
  std::string deltas;
  auto answer = llm.complete({{"user", "hi", 0}}, [&](const auto& s) { deltas += s; }, {});
  CHECK(answer.ok() && answer.value() == "你好" && deltas == "你好");
  CHECK(http.requests[0].headers.count("Authorization") == 0);
  CHECK(http.requests[0].headers.at("authorization") == "Bearer test-placeholder");
  CHECK(http.requests[0].headers.count("Content-Type") == 0);
  CHECK(http.requests[0].headers.at("content-type") == "application/json");
  http.requests.clear(); http.fail_after_stream = true;
  CHECK(!llm.complete({}, {}, {}).ok());
  CHECK(http.requests.size() == 1 && http.retries == 0);
  http.fail_after_stream = false;
  auto custom_config = c;
  custom_config.llm.auth_header = false;
  OpenAiCompatibleLlmProvider custom_llm(http, custom_config);
  CHECK(custom_llm.complete({}, {}, {}).ok());
  CHECK(http.requests.back().headers.at("authorization") == "Bearer stale-placeholder");
  for (const auto& broken : {std::string("data: {bad}\n\n"),
      std::string("data: {\"choices\":[{\"delta\":{\"content\":\"unfinished\"}}]}\n\n"),
      std::string("data: {\"error\":{}}\n\n"),
      std::string("data: {\"choices\":[{\"delta\":{\"tool_calls\":[]},\"finish_reason\":\"tool_calls\"}]}\n\n")}) {
    http.stream = broken;
    CHECK(!llm.complete({}, {}, {}).ok());
  }
}
void retryAndSecurity() {
  auto c = config();
  for (const auto error : {AudioError::kNetworkError, AudioError::kRateLimited,
                          AudioError::kAuthenticationError, AudioError::kProviderError,
                          AudioError::kTimeout}) {
    FakeHttp http; http.fail_first = error;
    http.json(R"({"choices":[{"message":{"content":"ok"}}]})");
    DashScopeAsrProvider asr(http, c);
    const auto result = asr.transcribe(std::vector<std::int16_t>(320), {});
    const bool retry = error == AudioError::kNetworkError || error == AudioError::kRateLimited;
    CHECK(result.ok() == retry);
    CHECK(http.requests.size() == (retry ? 2U : 1U));
  }
  CurlHttpClient real;
  HttpRequest insecure; insecure.url = "http://localhost.evil.invalid";
  CHECK(real.perform(insecure, {}).status().code() == AudioError::kConfigError);
  HttpRequest cancelled; cancelled.url = "https://example.invalid";
  CHECK(real.perform(cancelled, [] { return true; }).status().code() == AudioError::kCancelled);
}
void translationRequestOptions() {
  auto c = config();
  c.llm.name = "deepseek";
  c.retry_count = 0;
  c.llm_timeout_ms = 12345;
  FakeHttp http;
  http.stream = "data: {\"choices\":[{\"delta\":{\"content\":\"日本語\"}}]}\n\n"
                "data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}]}\n\n"
                "data: [DONE]\n\n";
  OpenAiCompatibleLlmProvider translator(http, c, true, true);
  const auto result = translator.complete(
      {{"system", "translation rules", 0}, {"user", "source answer", 0}}, {}, {});
  CHECK(result.ok() && result.value() == "日本語" && http.requests.size() == 1 && http.retries == 0);
  CHECK(http.requests[0].total_timeout_ms == 12345);
  auto body = JsonValue::parse(std::string(http.requests[0].body.begin(), http.requests[0].body.end()));
  CHECK(body.ok() && body.value().find("thinking")->find("type")->stringOr() == "disabled");
  CHECK(body.value().find("messages")->array().size() == 2);
  http.requests.clear();
  http.stream = "data: {\"choices\":[{\"delta\":{\"content\":\"partial\"}}]}\n\n"
                "data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"length\"}]}\n\n"
                "data: [DONE]\n\n";
  CHECK(!translator.complete({{"user", "source", 0}}, {}, {}).ok());
}
}
int main() {
  asrAndTts(); strictCloudJson(); llmStreams(); retryAndSecurity(); translationRequestOptions();
  return failures == 0 ? 0 : 1;
}
