#include "rootlink/voice/providers.h"

#if defined(ROOTLINK_SERVICE_API_CURL)

#include <chrono>
#include <algorithm>
#include <cctype>
#include <cstring>
#include <json-c/json.h>
#include <thread>

#include "rootlink/voice/codec.h"

namespace rootlink::voice {
namespace {

std::string trimSlash(std::string value) {
  while (!value.empty() && value.back() == '/') value.pop_back();
  return value;
}
std::vector<std::uint8_t> bytes(const std::string& value) {
  return {value.begin(), value.end()};
}
std::map<std::string, std::string> headers(const ProviderConfig& provider, bool sse = false) {
  // HTTP 字段名不区分大小写。先规范化，避免私有配置里的 Authorization 与
  // 环境密钥生成的 authorization 同时发出，让密钥优先级在实际请求中失效。
  std::map<std::string, std::string> output;
  for (const auto& [name, value] : provider.headers) {
    std::string key = name;
    std::transform(key.begin(), key.end(), key.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    output[key] = value;
  }
  output["content-type"] = "application/json";
  output["accept"] = sse ? "text/event-stream" : "application/json";
  if (provider.auth_header && !provider.api_key.empty())
    output["authorization"] = "Bearer " + provider.api_key;
  return output;
}
json_object* member(json_object* object, const char* key) {
  json_object* value = nullptr;
  return object != nullptr && json_object_is_type(object, json_type_object) &&
         json_object_object_get_ex(object, key, &value) ? value : nullptr;
}
std::string jsonString(json_object* object) {
  return object != nullptr && json_object_get_type(object) == json_type_string
             ? json_object_get_string(object)
             : std::string();
}
audio::Result<json_object*> parseJson(const std::vector<std::uint8_t>& body) {
  if (body.empty() || body.size() > 2U * 1024U * 1024U)
    return audio::Result<json_object*>(audio::Status(audio::AudioError::kProviderError,
                                                     "供应商 JSON 为空或超过 2 MiB"));
  json_tokener* tokener = json_tokener_new();
  if (!tokener)
    return audio::Result<json_object*>(audio::Status(audio::AudioError::kProviderError,
                                                     "无法分配 JSON 解析器"));
  // json-c 默认允许注释、尾随逗号或只解析第一个对象。云响应必须完整且严格，
  // 否则截断/拼接的 SSE 片段可能被误认为成功回答。
  json_tokener_set_flags(tokener, JSON_TOKENER_STRICT);
  json_object* result = json_tokener_parse_ex(tokener,
      reinterpret_cast<const char*>(body.data()), static_cast<int>(body.size()));
  const json_tokener_error error = json_tokener_get_error(tokener);
  std::size_t consumed = json_tokener_get_parse_end(tokener);
  while (consumed < body.size() && (body[consumed] == ' ' || body[consumed] == '\t' ||
         body[consumed] == '\r' || body[consumed] == '\n')) ++consumed;
  json_tokener_free(tokener);
  if (error != json_tokener_success || result == nullptr || consumed != body.size())
  {
    if (result) json_object_put(result);
    return audio::Result<json_object*>(audio::Status(audio::AudioError::kProviderError,
                                                     "供应商返回了无法解析的 JSON"));
  }
  return audio::Result<json_object*>(result);
}
audio::Result<HttpResponse> requestWithRetry(HttpClient& http, const HttpRequest& request,
                                             std::size_t retries, const StopRequested& stopped,
                                             const std::function<audio::Status(const char*, std::size_t)>& stream = {},
                                             const bool* response_started = nullptr) {
  audio::Status last(audio::AudioError::kNetworkError, "网络请求失败");
  for (std::size_t attempt = 0; attempt <= retries; ++attempt) {
    if (stopped && stopped())
      return audio::Result<HttpResponse>(audio::Status(audio::AudioError::kCancelled, "请求已取消"));
    auto result = http.perform(request, stopped, stream);
    if (result.ok()) return result;
    last = result.status();
    if (last.code() != audio::AudioError::kNetworkError &&
        last.code() != audio::AudioError::kRateLimited) break;
    // 流式回答一旦已有正文，重发请求会把开头重复给用户；因此中途断流必须原样失败。
    if (response_started != nullptr && *response_started) break;
    if (attempt == retries || (stopped && stopped())) break;
    http.noteRetry();
    for (int tick = 0; tick < 10 && !(stopped && stopped()); ++tick)
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  return audio::Result<HttpResponse>(last);
}

}  // namespace

DashScopeAsrProvider::DashScopeAsrProvider(HttpClient& http, RuntimeConfig config)
    : http_(http), config_(std::move(config)) {}
void DashScopeAsrProvider::cancel() noexcept { http_.cancel(); }

audio::Result<std::string> DashScopeAsrProvider::transcribe(
    const std::vector<std::int16_t>& samples, const StopRequested& stopped) {
  if (samples.empty() || samples.size() > 16000U * 30U)
    return audio::Result<std::string>(audio::Status(audio::AudioError::kInvalidArgument,
                                                    "ASR 输入必须为非空且不超过 30 秒的 PCM"));
  if (config_.asr.api_key.empty())
    return audio::Result<std::string>(audio::Status(audio::AudioError::kAuthenticationError,
                                                    "缺少 " + config_.asr.api_key_env));
  const std::string data_uri = "data:audio/wav;base64," + base64Encode(pcm16ToWav(samples));
  json_object* root = json_object_new_object();
  json_object_object_add(root, "model", json_object_new_string(config_.asr.model.c_str()));
  json_object* messages = json_object_new_array();
  json_object* message = json_object_new_object();
  json_object_object_add(message, "role", json_object_new_string("user"));
  json_object* content = json_object_new_array();
  json_object* audio = json_object_new_object();
  json_object_object_add(audio, "type", json_object_new_string("input_audio"));
  json_object* input_audio = json_object_new_object();
  json_object_object_add(input_audio, "data", json_object_new_string(data_uri.c_str()));
  json_object_object_add(audio, "input_audio", input_audio);
  json_object_array_add(content, audio);
  json_object_object_add(message, "content", content);
  json_object_array_add(messages, message);
  json_object_object_add(root, "messages", messages);
  const std::string payload = json_object_to_json_string_ext(root, JSON_C_TO_STRING_PLAIN);
  json_object_put(root);

  HttpRequest request;
  request.url = trimSlash(config_.asr.base_url) + "/chat/completions";
  request.headers = headers(config_.asr);
  request.body = bytes(payload);
  request.connect_timeout_ms = config_.connect_timeout_ms;
  request.total_timeout_ms = config_.asr_timeout_ms;
  request.response_limit = config_.max_json_bytes;
  auto response = requestWithRetry(http_, request, config_.retry_count, stopped);
  if (!response.ok()) return audio::Result<std::string>(response.status());
  auto parsed = parseJson(response.value().body);
  if (!parsed.ok()) return audio::Result<std::string>(parsed.status());
  json_object* root_response = parsed.value();
  json_object* choices = member(root_response, "choices");
  json_object* first = choices != nullptr && json_object_is_type(choices, json_type_array) && json_object_array_length(choices) > 0
                           ? json_object_array_get_idx(choices, 0)
                           : nullptr;
  std::string transcription = jsonString(member(member(first, "message"), "content"));
  json_object_put(root_response);
  if (transcription.empty())
    return audio::Result<std::string>(audio::Status(audio::AudioError::kProviderError,
                                                    "ASR 响应中没有识别文本"));
  return audio::Result<std::string>(std::move(transcription));
}

OpenAiCompatibleLlmProvider::OpenAiCompatibleLlmProvider(HttpClient& http, RuntimeConfig config)
    : http_(http), config_(std::move(config)) {}
void OpenAiCompatibleLlmProvider::cancel() noexcept { http_.cancel(); }

audio::Result<std::string> OpenAiCompatibleLlmProvider::complete(
    const std::vector<ChatMessage>& messages, const TextDelta& on_delta,
    const StopRequested& stopped) {
  if (config_.llm.auth_header && config_.llm.api_key.empty())
    return audio::Result<std::string>(audio::Status(audio::AudioError::kAuthenticationError,
                                                    "缺少 " + config_.llm.api_key_env));
  json_object* root = json_object_new_object();
  json_object_object_add(root, "model", json_object_new_string(config_.llm.model.c_str()));
  json_object_object_add(root, "stream", json_object_new_boolean(1));
  json_object_object_add(root, "temperature", json_object_new_double(0.7));
  json_object_object_add(root, "max_tokens", json_object_new_int(2048));
  json_object* message_array = json_object_new_array();
  for (const ChatMessage& item : messages) {
    json_object* message = json_object_new_object();
    json_object_object_add(message, "role", json_object_new_string(item.role.c_str()));
    json_object_object_add(message, "content", json_object_new_string(item.content.c_str()));
    json_object_array_add(message_array, message);
  }
  json_object_object_add(root, "messages", message_array);
  const std::string payload = json_object_to_json_string_ext(root, JSON_C_TO_STRING_PLAIN);
  json_object_put(root);

  HttpRequest request;
  request.url = trimSlash(config_.llm.base_url) + config_.llm.chat_path;
  if (payload.size() > config_.max_json_bytes)
    return audio::Result<std::string>(audio::Status(audio::AudioError::kConfigError, "LLM 请求超过 2 MiB 上限"));
  request.headers = headers(config_.llm, true);
  request.body = bytes(payload);
  request.connect_timeout_ms = config_.connect_timeout_ms;
  request.total_timeout_ms = config_.llm_timeout_ms;
  request.response_limit = config_.max_json_bytes;
  request.stream = true;
  SseParser parser;
  std::string answer;
  std::string minimax_cumulative;
  bool began = false;
  bool received = false;
  bool done = false;
  bool tools_seen = false;
  auto consume = [&](const SseEvent& event) -> audio::Status {
    if (done) return audio::Status::okStatus();
    if (event.data == "[DONE]") { done = true; return audio::Status::okStatus(); }
    const std::vector<std::uint8_t> event_bytes(event.data.begin(), event.data.end());
    auto parsed = parseJson(event_bytes);
    if (!parsed.ok()) return parsed.status();
    json_object* data = parsed.value();
    if (member(data, "error")) {
      json_object_put(data);
      return {audio::AudioError::kProviderError, "LLM SSE 返回错误事件"};
    }
    json_object* choices = member(data, "choices");
    json_object* first = choices != nullptr && json_object_is_type(choices, json_type_array) && json_object_array_length(choices) > 0
                             ? json_object_array_get_idx(choices, 0)
                             : nullptr;
    json_object* delta = member(first, "delta");
    // 推理片段不送给 TTS、不持久化；工具字段只识别，不执行、不拼接成角色正文。
    const auto reasoning = jsonString(member(delta, "reasoning_content"));
    (void)reasoning;
    if (member(delta, "tool_calls")) tools_seen = true;
    if (!jsonString(member(first, "finish_reason")).empty()) done = true;
    std::string chunk = jsonString(member(delta, "content"));
    if (chunk.empty()) chunk = jsonString(member(delta, "text"));
    if (config_.llm.name == "minimax" && !chunk.empty()) {
      if (chunk.rfind(minimax_cumulative, 0) == 0) {
        const std::string next = chunk.substr(minimax_cumulative.size());
        minimax_cumulative = chunk;
        chunk = next;
      } else {
        minimax_cumulative += chunk;
      }
    }
    if (!chunk.empty()) {
      began = true;
      answer += chunk;
      if (on_delta) on_delta(chunk);
    }
    json_object_put(data);
    return audio::Status::okStatus();
  };
  const auto stream_callback = [&](const char* data, std::size_t size) {
    received = received || size > 0;
    for (const SseEvent& event : parser.feed(data, size)) {
      const audio::Status status = consume(event);
      if (!status.ok()) return status;
    }
    return audio::Status::okStatus();
  };
  // 一旦收到正文就禁用自动重试，避免中途断流后向用户重复一遍回答。
  auto response = requestWithRetry(http_, request, config_.retry_count, stopped,
                                   stream_callback, &received);
  if (!response.ok()) return audio::Result<std::string>(response.status());
  for (const SseEvent& event : parser.finish()) {
    const auto status = consume(event);
    if (!status.ok()) return audio::Result<std::string>(status);
  }
  if (!done || tools_seen)
    return audio::Result<std::string>(audio::Status(audio::AudioError::kProviderError,
        tools_seen ? "Stage 2 不执行 LLM 工具调用" : "LLM SSE 在结束标记之前中断"));
  if (!began || answer.empty())
    return audio::Result<std::string>(audio::Status(audio::AudioError::kProviderError,
                                                    "LLM 响应中没有正文"));
  return audio::Result<std::string>(std::move(answer));
}

DashScopeTtsProvider::DashScopeTtsProvider(HttpClient& http, RuntimeConfig config)
    : http_(http), config_(std::move(config)) {}
void DashScopeTtsProvider::cancel() noexcept { http_.cancel(); }

audio::Result<std::vector<std::int16_t>> DashScopeTtsProvider::synthesize(
    const std::string& input_text, const StopRequested& stopped) {
  if (input_text.empty() || input_text.size() > 24000)
    return audio::Result<std::vector<std::int16_t>>(audio::Status(
        audio::AudioError::kInvalidArgument, "TTS 文本为空或超过 24000 字节安全上限"));
  if (config_.tts.api_key.empty())
    return audio::Result<std::vector<std::int16_t>>(audio::Status(
        audio::AudioError::kAuthenticationError, "缺少 " + config_.tts.api_key_env));
  json_object* root = json_object_new_object();
  json_object_object_add(root, "model", json_object_new_string(config_.tts.model.c_str()));
  json_object* input = json_object_new_object();
  json_object_object_add(input, "text", json_object_new_string(input_text.c_str()));
  json_object_object_add(root, "input", input);
  // CosyVoice HTTP 协议将合成选项放在 input 内，而非其他 DashScope API 的 parameters。
  json_object_object_add(input, "voice", json_object_new_string(config_.tts_voice.c_str()));
  json_object_object_add(input, "format", json_object_new_string("wav"));
  json_object_object_add(input, "sample_rate", json_object_new_int(16000));
  const std::string payload = json_object_to_json_string_ext(root, JSON_C_TO_STRING_PLAIN);
  json_object_put(root);

  HttpRequest request;
  request.url = trimSlash(config_.tts.base_url) + "/services/audio/tts/SpeechSynthesizer";
  request.headers = headers(config_.tts);
  request.body = bytes(payload);
  request.connect_timeout_ms = config_.connect_timeout_ms;
  request.total_timeout_ms = config_.tts_timeout_ms;
  request.response_limit = config_.max_json_bytes;
  auto response = requestWithRetry(http_, request, config_.retry_count, stopped);
  if (!response.ok()) return audio::Result<std::vector<std::int16_t>>(response.status());
  auto parsed = parseJson(response.value().body);
  if (!parsed.ok()) return audio::Result<std::vector<std::int16_t>>(parsed.status());
  json_object* root_response = parsed.value();
  json_object* output = member(root_response, "output");
  std::string url = jsonString(member(output, "audio_url"));
  if (url.empty()) url = jsonString(member(member(output, "audio"), "url"));
  json_object_put(root_response);
  // DashScope may return signed HTTP OSS URLs. Upgrade only its OSS endpoint;
  // preserve path/query byte-for-byte and never send the API key to storage.
  if (url.rfind("http://", 0) == 0) {
    const auto end = url.find('/', 7);
    const std::string host = url.substr(7, end == std::string::npos ? end : end - 7);
    const std::string suffix = ".aliyuncs.com";
    if (host.size() > suffix.size() &&
        host.compare(host.size() - suffix.size(), suffix.size(), suffix) == 0 &&
        host.find(".oss-") != std::string::npos &&
        host.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789.-") == std::string::npos)
      url.replace(0, 7, "https://");
  }
  if (url.rfind("https://", 0) != 0)
    return audio::Result<std::vector<std::int16_t>>(audio::Status(
        audio::AudioError::kProviderError, "TTS 响应未包含安全的 HTTPS 音频地址"));
  HttpRequest download;
  download.method = "GET";
  download.url = url;
  download.connect_timeout_ms = config_.connect_timeout_ms;
  download.total_timeout_ms = config_.tts_timeout_ms;
  download.response_limit = config_.max_tts_bytes;
  auto audio_response = requestWithRetry(http_, download, config_.retry_count, stopped);
  if (!audio_response.ok())
    return audio::Result<std::vector<std::int16_t>>(audio_response.status());
  return wavToPcm16(audio_response.value().body, true);
}

}  // namespace rootlink::voice
#endif
