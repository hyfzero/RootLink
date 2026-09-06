#include "rootlink/voice/providers.h"

#if defined(ROOTLINK_SERVICE_API_CURL)

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <curl/curl.h>
#include <mutex>
#include <filesystem>
#include <fstream>

namespace rootlink::voice {
namespace {

struct TransferContext {
  HttpResponse* response{nullptr};
  const HttpRequest* request{nullptr};
  const StopRequested* stopped{nullptr};
  const std::atomic<bool>* cancelled{nullptr};
  const std::function<audio::Status(const char*, std::size_t)>* stream_chunk{nullptr};
  audio::Status callback_status;
  std::size_t received_bytes{0};
  std::size_t header_bytes{0};
};

std::size_t writeBody(char* data, std::size_t size, std::size_t count, void* user_data) {
  auto& context = *static_cast<TransferContext*>(user_data);
  const std::size_t bytes = size * count;
  if (bytes > context.request->response_limit -
                  std::min(context.received_bytes, context.request->response_limit)) {
    context.callback_status = {audio::AudioError::kProviderError, "HTTP 响应超过配置上限"};
    return 0;
  }
  context.received_bytes += bytes;
  if (context.response->status_code >= 200 && context.response->status_code < 300 &&
      context.stream_chunk != nullptr && *context.stream_chunk) {
    const audio::Status status = (*context.stream_chunk)(data, bytes);
    if (!status.ok()) {
      context.callback_status = status;
      return 0;
    }
    return bytes;
  }
  const auto* begin = reinterpret_cast<const std::uint8_t*>(data);
  context.response->body.insert(context.response->body.end(), begin, begin + bytes);
  return bytes;
}

std::size_t writeHeader(char* data, std::size_t size, std::size_t count, void* user_data) {
  auto& context = *static_cast<TransferContext*>(user_data);
  const std::size_t bytes = size * count;
  context.header_bytes += bytes;
  if (context.header_bytes > 64U * 1024U) {
    context.callback_status = {audio::AudioError::kProviderError, "HTTP 响应头超过上限"};
    return 0;
  }
  std::string line(data, bytes);
  if (line.rfind("HTTP/", 0) == 0) {
    const auto space = line.find(' ');
    if (space != std::string::npos)
      context.response->status_code = std::strtol(line.c_str() + space + 1, nullptr, 10);
    context.response->headers.clear();
  }
  const std::size_t colon = line.find(':');
  if (colon != std::string::npos) {
    std::string key = line.substr(0, colon);
    std::transform(key.begin(), key.end(), key.begin(),
                   [](unsigned char value) { return static_cast<char>(std::tolower(value)); });
    std::size_t begin = colon + 1;
    while (begin < line.size() && std::isspace(static_cast<unsigned char>(line[begin]))) ++begin;
    std::size_t end = line.size();
    while (end > begin && std::isspace(static_cast<unsigned char>(line[end - 1]))) --end;
    context.response->headers[key] = line.substr(begin, end - begin);
  }
  return bytes;
}

int progress(void* user_data, curl_off_t, curl_off_t, curl_off_t, curl_off_t) {
  const auto& context = *static_cast<TransferContext*>(user_data);
  return context.cancelled->load() || (context.stopped != nullptr && *context.stopped &&
                                      (*context.stopped)())
             ? 1
             : 0;
}

audio::AudioError mapHttpStatus(long status) {
  if (status == 401 || status == 403) return audio::AudioError::kAuthenticationError;
  if (status == 429) return audio::AudioError::kRateLimited;
  if (status >= 500 && status <= 599) return audio::AudioError::kNetworkError;
  if (status >= 400 && status <= 499) return audio::AudioError::kConfigError;
  return audio::AudioError::kProviderError;
}

}  // namespace

CurlHttpClient::CurlHttpClient() {
  static std::once_flag initialized;
  std::call_once(initialized, [] { curl_global_init(CURL_GLOBAL_DEFAULT); });
}
CurlHttpClient::~CurlHttpClient() { cancel(); }
audio::Status CurlHttpClient::checkEnvironment() const {
  const auto* version = curl_version_info(CURLVERSION_NOW);
  if (!version || !(version->features & CURL_VERSION_SSL))
    return {audio::AudioError::kConfigError, "libcurl 未启用 TLS，请启用 Buildroot OpenSSL/libcurl"};
  bool https = false;
  for (auto protocol = version->protocols; protocol && *protocol; ++protocol)
    if (std::string(*protocol) == "https") https = true;
  if (!https) return {audio::AudioError::kConfigError, "libcurl 未启用 HTTPS 协议"};
  bool readable = false;
#if LIBCURL_VERSION_NUM >= 0x075400
  CURL* handle = curl_easy_init();
  if (handle) {
    char* bundle = nullptr;
    char* directory = nullptr;
    curl_easy_getinfo(handle, CURLINFO_CAINFO, &bundle);
    curl_easy_getinfo(handle, CURLINFO_CAPATH, &directory);
    if (bundle && std::ifstream(bundle).good()) readable = true;
    std::error_code ec;
    if (directory && std::filesystem::is_directory(directory, ec) &&
        !std::filesystem::is_empty(directory, ec) && !ec) readable = true;
    curl_easy_cleanup(handle);
  }
#else
  readable = std::ifstream("/etc/ssl/certs/ca-certificates.crt").good();
#endif
  return readable ? audio::Status::okStatus() : audio::Status(
      audio::AudioError::kConfigError, "找不到可读的 CA 信任库，请安装 ca-certificates 并检查系统时间");
}
void CurlHttpClient::cancel() noexcept { cancelled_.store(true); }
HttpClientStats CurlHttpClient::stats() const noexcept {
  return {requests_.load(), retries_.load(), authentication_errors_.load(),
          rate_limit_errors_.load(), provider_errors_.load()};
}

audio::Result<HttpResponse> CurlHttpClient::perform(
    const HttpRequest& request, const StopRequested& stopped,
    const std::function<audio::Status(const char*, std::size_t)>& stream_chunk) {
  cancelled_.store(false);
  if (stopped && stopped())
    return audio::Result<HttpResponse>(audio::Status(audio::AudioError::kCancelled, "HTTP 请求已取消"));
  ++requests_;
  if (request.url.rfind("https://", 0) != 0) {
    return audio::Result<HttpResponse>(audio::Status(audio::AudioError::kConfigError,
                                                     "云端 URL 必须使用 HTTPS"));
  }
  CURL* handle = curl_easy_init();
  if (handle == nullptr)
    return audio::Result<HttpResponse>(audio::Status(audio::AudioError::kNetworkError,
                                                     "无法初始化 libcurl"));
  HttpResponse response;
  TransferContext context{&response, &request, &stopped, &cancelled_, &stream_chunk, {}, 0};
  curl_slist* headers = nullptr;
  for (const auto& [key, value] : request.headers)
    headers = curl_slist_append(headers, (key + ": " + value).c_str());
  curl_easy_setopt(handle, CURLOPT_URL, request.url.c_str());
  curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT_MS, request.connect_timeout_ms);
  curl_easy_setopt(handle, CURLOPT_TIMEOUT_MS, request.total_timeout_ms);
  curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
  curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
  // 带认证的 POST 不跟随重定向，避免自定义密钥头跨主机泄露；无认证音频 GET 可跳转。
  curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, request.method == "GET" ? 1L : 0L);
  curl_easy_setopt(handle, CURLOPT_MAXREDIRS, 3L);
#if LIBCURL_VERSION_NUM >= 0x075500
  curl_easy_setopt(handle, CURLOPT_PROTOCOLS_STR, "https");
  curl_easy_setopt(handle, CURLOPT_REDIR_PROTOCOLS_STR, "https");
#else
  curl_easy_setopt(handle, CURLOPT_PROTOCOLS, CURLPROTO_HTTPS);
  curl_easy_setopt(handle, CURLOPT_REDIR_PROTOCOLS, CURLPROTO_HTTPS);
#endif
  curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, writeBody);
  curl_easy_setopt(handle, CURLOPT_WRITEDATA, &context);
  curl_easy_setopt(handle, CURLOPT_HEADERFUNCTION, writeHeader);
  curl_easy_setopt(handle, CURLOPT_HEADERDATA, &context);
  curl_easy_setopt(handle, CURLOPT_XFERINFOFUNCTION, progress);
  curl_easy_setopt(handle, CURLOPT_XFERINFODATA, &context);
  curl_easy_setopt(handle, CURLOPT_NOPROGRESS, 0L);
  curl_easy_setopt(handle, CURLOPT_USERAGENT, "RootLink-RV1106/0.2");
  if (request.method == "POST") {
    curl_easy_setopt(handle, CURLOPT_POST, 1L);
    curl_easy_setopt(handle, CURLOPT_POSTFIELDS, request.body.empty() ? "" :
                     reinterpret_cast<const char*>(request.body.data()));
    curl_easy_setopt(handle, CURLOPT_POSTFIELDSIZE_LARGE, static_cast<curl_off_t>(request.body.size()));
  }
  const CURLcode result = curl_easy_perform(handle);
  curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &response.status_code);
  curl_slist_free_all(headers);
  curl_easy_cleanup(handle);
  if (!context.callback_status.ok()) return audio::Result<HttpResponse>(context.callback_status);
  if (result != CURLE_OK) {
    if (cancelled_.load() || (stopped && stopped()))
      return audio::Result<HttpResponse>(audio::Status(audio::AudioError::kCancelled, "HTTP 请求已取消"));
    const bool connection_failure = context.received_bytes == 0 &&
        (result == CURLE_COULDNT_CONNECT || result == CURLE_COULDNT_RESOLVE_HOST ||
         result == CURLE_COULDNT_RESOLVE_PROXY);
    const bool tls_failure = result == CURLE_PEER_FAILED_VERIFICATION ||
                             result == CURLE_SSL_CACERT_BADFILE;
    return audio::Result<HttpResponse>(audio::Status(tls_failure ? audio::AudioError::kConfigError :
        connection_failure ? audio::AudioError::kNetworkError : audio::AudioError::kTimeout,
                                                     std::string("HTTP 请求失败：") + curl_easy_strerror(result)));
  }
  if (response.status_code < 200 || response.status_code >= 300) {
    const audio::AudioError code = mapHttpStatus(response.status_code);
    if (code == audio::AudioError::kAuthenticationError) ++authentication_errors_;
    else if (code == audio::AudioError::kRateLimited) ++rate_limit_errors_;
    else if (code == audio::AudioError::kProviderError) ++provider_errors_;
    return audio::Result<HttpResponse>(audio::Status(
        code, "云端请求失败（HTTP " + std::to_string(response.status_code) + "）"));
  }
  return audio::Result<HttpResponse>(std::move(response));
}

}  // namespace rootlink::voice
#endif
