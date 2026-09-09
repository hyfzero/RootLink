#include "rootlink/voice/runtime_config.h"

#include <cstdlib>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <limits>
#include <sstream>
#include <unordered_map>

#include "rootlink/voice/json_value.h"

namespace rootlink::voice {
namespace {

using Values = std::unordered_map<std::string, std::string>;

audio::Result<Values> readKeyValues(const std::string& path, bool optional) {
  std::ifstream input(path);
  if (!input) {
    if (optional) return audio::Result<Values>(Values{});
    return audio::Result<Values>(audio::Status(audio::AudioError::kConfigError,
                                               "无法打开配置文件：" + path));
  }
  Values values;
  std::error_code size_error;
  if (std::filesystem::file_size(path, size_error) > 1024 * 1024 || size_error)
    return audio::Result<Values>(audio::Status(audio::AudioError::kConfigError,
                                               "配置文件不可读或超过 1 MiB"));
  std::string line;
  std::size_t line_number = 0;
  while (std::getline(input, line)) {
    ++line_number;
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.empty() || line.front() == '#') continue;
    const std::size_t equal = line.find('=');
    if (equal == std::string::npos || equal == 0) {
      return audio::Result<Values>(audio::Status(
          audio::AudioError::kConfigError,
          "配置第 " + std::to_string(line_number) + " 行必须是 KEY=VALUE"));
    }
    values[line.substr(0, equal)] = line.substr(equal + 1);
  }
  return audio::Result<Values>(std::move(values));
}

template <typename T>
bool parseUnsigned(const Values& values, const char* key, T& output) {
  const auto found = values.find(key);
  if (found == values.end()) return true;
  try {
    std::size_t used = 0;
    const unsigned long long parsed = std::stoull(found->second, &used);
    if (found->second.empty() || found->second.front() == '-' || used != found->second.size() ||
        parsed > static_cast<unsigned long long>(std::numeric_limits<T>::max())) return false;
    output = static_cast<T>(parsed);
    return true;
  } catch (...) {
    return false;
  }
}

bool parseDouble(const Values& values, const char* key, double& output) {
  const auto found = values.find(key);
  if (found == values.end()) return true;
  try {
    std::size_t used = 0;
    output = std::stod(found->second, &used);
    return used == found->second.size() && std::isfinite(output);
  } catch (...) {
    return false;
  }
}

void stringValue(const Values& values, const char* key, std::string& output) {
  const auto found = values.find(key);
  if (found != values.end()) output = found->second;
}

std::string readWholeFile(const std::string& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) return {};
  input.seekg(0, std::ios::end);
  if (input.tellg() > 1024 * 1024) return "INVALID_OVERSIZE_JSON";
  input.seekg(0);
  std::ostringstream output;
  output << input.rdbuf();
  return output.str();
}

std::string envNameForProvider(const std::string& provider) {
  if (provider == "qwen" || provider == "dashscope") return "DASHSCOPE_API_KEY";
  if (provider == "deepseek") return "DEEPSEEK_API_KEY";
  if (provider == "glm") return "GLM_API_KEY";
  if (provider == "moonshot" || provider == "kimi") return "MOONSHOT_API_KEY";
  if (provider == "minimax") return "MINIMAX_API_KEY";
  return {};
}

void overrideFromEnvironment(Values& values) {
  // 普通运行参数也允许通过环境变量覆盖；密钥在后面单独处理，以确保永远不会
  // 因调试输出整个配置表而意外泄露。
  static constexpr const char* keys[] = {
      "TARGET", "AUDIO_API", "SERVICE_MODE", "CAPTURE_DEVICE", "PLAYBACK_DEVICE",
      "UI_BACKEND", "UI_DEVICE", "UI_INPUT_DEVICE", "UI_WIDTH", "UI_HEIGHT", "UI_TEXT_INTERVAL_MS",
      "BUFFER_FRAMES", "ASR_PROVIDER", "ASR_MODEL", "ASR_BASE_URL", "LLM_PROVIDER",
      "LLM_MODEL", "LLM_BASE_URL", "TTS_PROVIDER", "TTS_MODEL", "TTS_BASE_URL",
      "TTS_VOICE", "TTS_SAMPLE_RATE", "TTS_TRANSLATE_TO", "MODELS_FILE", "SECRETS_FILE", "ROLE_DIR",
      "SESSION_DIR", "HISTORY_TURNS", "HISTORY_TOKEN_BUDGET", "VAD_START_FRAMES",
      "VAD_PRE_ROLL_MS", "VAD_END_SILENCE_MS", "VAD_MIN_UTTERANCE_MS",
      "VAD_MAX_UTTERANCE_MS", "VAD_MIN_RMS", "VAD_NOISE_MULTIPLIER", "VAD_NOISE_ALPHA",
      "CONNECT_TIMEOUT_MS", "ASR_TIMEOUT_MS", "LLM_TIMEOUT_MS", "TTS_TIMEOUT_MS", "TTS_TRANSLATION_TIMEOUT_MS",
      "RETRY_COUNT", "PERSONA_BACKEND", "PYTHON_EXECUTABLE", "PYTHON_CORE_ENTRY", "PYTHON_DATA_DIR", "PERSONA_START_TIMEOUT_MS", "PERSONA_TURN_TIMEOUT_MS"};
  for (const char* key : keys) {
    if (const char* value = std::getenv(key); value != nullptr && *value != '\0') values[key] = value;
  }
}

audio::Status loadModelsJson(RuntimeConfig& config, const Values& explicit_values) {
  const std::string source = readWholeFile(config.models_file);
  if (source.empty()) return audio::Status::okStatus();
  const auto parsed = JsonValue::parse(source);
  if (!parsed.ok() || !parsed.value().isObject())
    return {audio::AudioError::kConfigError, "models.json 不是有效 JSON 对象或超过 1 MiB"};
  if (explicit_values.count("LLM_PROVIDER") == 0)
    if (const auto* value = parsed.value().find("default_provider"))
      config.llm.name = value->stringOr(config.llm.name);
  if (explicit_values.count("LLM_MODEL") == 0)
    if (const auto* value = parsed.value().find("default_model"))
      config.llm.model = value->stringOr(config.llm.model);
  if (config.llm.name != "qwen" && explicit_values.count("LLM_BASE_URL") == 0)
    config.llm.base_url.clear();
  const JsonValue* providers = parsed.value().find("providers");
  if (providers == nullptr || !providers->isObject())
    return {audio::AudioError::kConfigError, "models.json 缺少 providers 对象"};
  const JsonValue* provider = providers->find(config.llm.name);
  if (provider == nullptr || !provider->isObject())
    return {audio::AudioError::kConfigError, "models.json 中找不到所选 LLM_PROVIDER"};
  if (explicit_values.count("LLM_BASE_URL") == 0)
    if (const JsonValue* value = provider->find("base_url"))
      config.llm.base_url = value->stringOr(config.llm.base_url);
  if (const auto* value = provider->find("chat_path"))
    config.llm.chat_path = value->stringOr(config.llm.chat_path);
  if (const auto* value = provider->find("api_type"))
    if (value->stringOr("openai") == "anthropic-messages")
      return {audio::AudioError::kConfigError, "Stage 2 仅支持 OpenAI 兼容接口，请配置兼容端点"};
  if (const JsonValue* value = provider->find("api_key"))
    config.llm.api_key = value->stringOr();
  if (const JsonValue* value = provider->find("auth_header"))
    config.llm.auth_header = value->boolOr(true);
  if (const JsonValue* value = provider->find("headers"); value != nullptr && value->isObject()) {
    for (const auto& [key, item] : value->object()) config.llm.headers[key] = item.stringOr();
  }
  return audio::Status::okStatus();
}

void resolveKey(ProviderConfig& provider, const Values& secrets) {
  if (provider.api_key_env.empty()) provider.api_key_env = envNameForProvider(provider.name);
  if (!provider.api_key_env.empty()) {
    if (const char* value = std::getenv(provider.api_key_env.c_str()); value != nullptr && *value != '\0') {
      provider.api_key = value;
      return;
    }
    const auto found = secrets.find(provider.api_key_env);
    if (found != secrets.end() && !found->second.empty()) provider.api_key = found->second;
  }
}

}  // namespace

audio::Status RuntimeConfig::validate() const {
  using audio::AudioError;
  if (target != "simulator" && target != "rv1106")
    return {AudioError::kConfigError, "TARGET 只能是 simulator 或 rv1106"};
  if (audio_api != "simulated" && audio_api != "alsa")
    return {AudioError::kConfigError, "AUDIO_API 只能是 simulated 或 alsa"};
  if (target == "rv1106" && audio_api != "alsa")
    return {AudioError::kConfigError, "RV1106 必须使用 ALSA"};
  if (service_mode != "mock" && service_mode != "cloud")
    return {AudioError::kConfigError, "SERVICE_MODE 只能是 mock 或 cloud"};
  if (buffer_frames == 0 || buffer_frames > 1000 || vad.start_frames == 0 ||
      vad.start_frames > 50 || vad.pre_roll_ms < vad.start_frames * 20 ||
      vad.pre_roll_ms > 1000 || vad.max_utterance_ms <= vad.pre_roll_ms + vad.start_frames * 20 ||
      vad.max_utterance_ms > 30000 || vad.end_silence_ms == 0 ||
      vad.end_silence_ms >= vad.max_utterance_ms || vad.min_utterance_ms == 0 ||
      !std::isfinite(vad.min_rms) || !std::isfinite(vad.noise_multiplier) ||
      !std::isfinite(vad.noise_alpha) || vad.pre_roll_ms % 20 != 0 ||
      vad.end_silence_ms % 20 != 0 || vad.min_utterance_ms % 20 != 0 ||
      vad.max_utterance_ms % 20 != 0 || vad.min_utterance_ms > vad.max_utterance_ms ||
      vad.noise_alpha <= 0.0 || vad.noise_alpha > 1.0 || vad.noise_multiplier <= 1.0 ||
      vad.min_rms <= 0.0 || vad.min_rms > 32767.0) {
    return {AudioError::kConfigError, "VAD 和缓冲参数无效；毫秒项必须是 20ms 的整数倍"};
  }
  if (retry_count > 1 || connect_timeout_ms <= 0 || asr_timeout_ms <= 0 ||
      llm_timeout_ms <= 0 || tts_timeout_ms <= 0 || tts_translation_timeout_ms < 1 || connect_timeout_ms > 60000 ||
      asr_timeout_ms > 300000 || llm_timeout_ms > 300000 || tts_timeout_ms > 300000 || tts_translation_timeout_ms > 300000 ||
      history_turns > 100 || history_token_budget > 12000)
    return {AudioError::kConfigError, "超时、历史预算或重试配置超出安全范围"};
  if (service_mode == "cloud" && (audio_api != "alsa" || asr.name != "dashscope" ||
      tts.name != "dashscope"))
    return {AudioError::kConfigError, "cloud 模式需要 ALSA 和 DashScope ASR/TTS"};
  if (service_mode == "mock" && (target != "simulator" || audio_api != "simulated"))
    return {AudioError::kConfigError, "mock 模式需要 simulator + simulated"};
  if (llm.chat_path.empty() || llm.chat_path.front() != '/' ||
      llm.chat_path.find_first_of("\r\n") != std::string::npos)
    return {AudioError::kConfigError, "LLM chat_path 必须是以 / 开始的路径"};
  if (service_mode == "cloud") {
    for (const auto* provider : {&asr, &llm, &tts}) {
      if (provider->base_url.rfind("https://", 0) != 0 || provider->model.empty())
        return {AudioError::kConfigError, "云端模型名不能为空且端点必须使用 HTTPS"};
      for (const auto& header : provider->headers)
        if (header.first.find_first_of("\r\n:") != std::string::npos ||
            header.second.find_first_of("\r\n") != std::string::npos)
          return {AudioError::kConfigError, "HTTP 头部配置包含非法字符"};
    }
  }
  if ((ui_backend != "none" && ui_backend != "sdl" && ui_backend != "fbdev") ||
      ui_device.empty() || ui_width < 80 || ui_height < 80 || ui_width > 1920 || ui_height > 1080 ||
      ui_text_interval_ms < 10 || ui_text_interval_ms > 1000)
    return {AudioError::kConfigError, "Invalid UI backend/device/size or UI_TEXT_INTERVAL_MS (10-1000)"};
  if ((persona_backend != "simple" && persona_backend != "python") ||
      persona_start_timeout_ms <= 0 || persona_turn_timeout_ms <= 0 ||
      (persona_backend == "python" && (python_executable.empty() || python_core_entry.empty() || python_data_dir.empty())))
    return {AudioError::kConfigError, "Invalid Python persona configuration"};
  if (tts_sample_rate != 16000)
    return {AudioError::kConfigError, "Stage 2 的 TTS_SAMPLE_RATE 必须是 16000"};
  if (tts_translate_to != "none" && tts_translate_to != "ja")
    return {AudioError::kConfigError, "TTS_TRANSLATE_TO 只能是 none 或 ja"};
  if (service_mode == "cloud" && tts.model.rfind("cosyvoice-v3.5", 0) == 0 &&
      (tts_voice.empty() || tts_voice.rfind(tts.model + "-", 0) != 0))
    return {AudioError::kConfigError,
            "CosyVoice v3.5 需要非空的克隆音色 ID，格式为 " + tts.model + "-{prefix}-{unique}"};
  if (service_mode == "cloud" &&
      (asr.base_url.empty() || llm.base_url.empty() || tts.base_url.empty()))
    return {AudioError::kConfigError, "cloud 模式的供应商 base_url 不能为空"};
  return audio::Status::okStatus();
}

audio::Result<RuntimeConfig> loadRuntimeConfig(const std::string& path) {
  auto values_result = readKeyValues(path, false);
  if (!values_result.ok()) return audio::Result<RuntimeConfig>(values_result.status());
  Values values = std::move(values_result.value());
  overrideFromEnvironment(values);
  RuntimeConfig config;
  stringValue(values, "UI_BACKEND", config.ui_backend);
  stringValue(values, "UI_DEVICE", config.ui_device);
  stringValue(values, "UI_INPUT_DEVICE", config.ui_input_device);
  stringValue(values, "PERSONA_BACKEND", config.persona_backend);
  stringValue(values, "PYTHON_EXECUTABLE", config.python_executable);
  stringValue(values, "PYTHON_CORE_ENTRY", config.python_core_entry);
  stringValue(values, "PYTHON_DATA_DIR", config.python_data_dir);
  stringValue(values, "TARGET", config.target);
  stringValue(values, "AUDIO_API", config.audio_api);
  stringValue(values, "SERVICE_MODE", config.service_mode);
  stringValue(values, "CAPTURE_DEVICE", config.capture_device);
  stringValue(values, "PLAYBACK_DEVICE", config.playback_device);
  stringValue(values, "ASR_PROVIDER", config.asr.name);
  stringValue(values, "ASR_MODEL", config.asr.model);
  stringValue(values, "ASR_BASE_URL", config.asr.base_url);
  stringValue(values, "LLM_PROVIDER", config.llm.name);
  stringValue(values, "LLM_MODEL", config.llm.model);
  stringValue(values, "LLM_BASE_URL", config.llm.base_url);
  stringValue(values, "TTS_PROVIDER", config.tts.name);
  stringValue(values, "TTS_MODEL", config.tts.model);
  stringValue(values, "TTS_BASE_URL", config.tts.base_url);
  stringValue(values, "TTS_VOICE", config.tts_voice);
  stringValue(values, "TTS_TRANSLATE_TO", config.tts_translate_to);
  stringValue(values, "MODELS_FILE", config.models_file);
  stringValue(values, "SECRETS_FILE", config.secrets_file);
  stringValue(values, "ROLE_DIR", config.role_dir);
  stringValue(values, "SESSION_DIR", config.session_dir);

  bool valid_numbers = true;
  valid_numbers &= parseUnsigned(values, "UI_WIDTH", config.ui_width);
  valid_numbers &= parseUnsigned(values, "UI_HEIGHT", config.ui_height);
  valid_numbers &= parseUnsigned(values, "UI_TEXT_INTERVAL_MS", config.ui_text_interval_ms);
  valid_numbers &= parseUnsigned(values, "PERSONA_START_TIMEOUT_MS", config.persona_start_timeout_ms);
  valid_numbers &= parseUnsigned(values, "PERSONA_TURN_TIMEOUT_MS", config.persona_turn_timeout_ms);
  valid_numbers &= parseUnsigned(values, "BUFFER_FRAMES", config.buffer_frames);
  valid_numbers &= parseUnsigned(values, "TTS_SAMPLE_RATE", config.tts_sample_rate);
  valid_numbers &= parseUnsigned(values, "HISTORY_TURNS", config.history_turns);
  valid_numbers &= parseUnsigned(values, "HISTORY_TOKEN_BUDGET", config.history_token_budget);
  valid_numbers &= parseUnsigned(values, "VAD_START_FRAMES", config.vad.start_frames);
  valid_numbers &= parseUnsigned(values, "VAD_PRE_ROLL_MS", config.vad.pre_roll_ms);
  valid_numbers &= parseUnsigned(values, "VAD_END_SILENCE_MS", config.vad.end_silence_ms);
  valid_numbers &= parseUnsigned(values, "VAD_MIN_UTTERANCE_MS", config.vad.min_utterance_ms);
  valid_numbers &= parseUnsigned(values, "VAD_MAX_UTTERANCE_MS", config.vad.max_utterance_ms);
  valid_numbers &= parseDouble(values, "VAD_MIN_RMS", config.vad.min_rms);
  valid_numbers &= parseDouble(values, "VAD_NOISE_MULTIPLIER", config.vad.noise_multiplier);
  valid_numbers &= parseDouble(values, "VAD_NOISE_ALPHA", config.vad.noise_alpha);
  valid_numbers &= parseUnsigned(values, "CONNECT_TIMEOUT_MS", config.connect_timeout_ms);
  valid_numbers &= parseUnsigned(values, "ASR_TIMEOUT_MS", config.asr_timeout_ms);
  valid_numbers &= parseUnsigned(values, "LLM_TIMEOUT_MS", config.llm_timeout_ms);
  valid_numbers &= parseUnsigned(values, "TTS_TIMEOUT_MS", config.tts_timeout_ms);
  valid_numbers &= parseUnsigned(values, "TTS_TRANSLATION_TIMEOUT_MS", config.tts_translation_timeout_ms);
  valid_numbers &= parseUnsigned(values, "RETRY_COUNT", config.retry_count);
  if (!valid_numbers)
    return audio::Result<RuntimeConfig>(audio::Status(audio::AudioError::kConfigError,
                                                      "配置中存在无效数字"));

  // 配置/环境中的显式项高于 models.json；缺省 provider/model 则继承 RootLink。
  if (config.llm.name != "qwen" && values.count("LLM_BASE_URL") == 0)
    config.llm.base_url.clear();
  const auto models_status = loadModelsJson(config, values);
  if (!models_status.ok()) return audio::Result<RuntimeConfig>(models_status);
  config.asr.api_key_env = envNameForProvider(config.asr.name);
  config.llm.api_key_env = envNameForProvider(config.llm.name);
  config.tts.api_key_env = envNameForProvider(config.tts.name);
  auto secrets = readKeyValues(config.secrets_file, true);
  if (!secrets.ok()) return audio::Result<RuntimeConfig>(secrets.status());
#if !defined(_WIN32)
  std::error_code permissions_error;
  const auto permissions = std::filesystem::status(config.secrets_file, permissions_error).permissions();
  const auto exposed = std::filesystem::perms::group_all | std::filesystem::perms::others_all;
  if (!permissions_error && (permissions & exposed) != std::filesystem::perms::none)
    config.warnings.push_back("密钥文件权限过宽，请执行 chmod 600 <密钥文件>；内容不会输出");
#endif
  if (secrets.ok()) {
    resolveKey(config.asr, secrets.value());
    resolveKey(config.llm, secrets.value());
    resolveKey(config.tts, secrets.value());
  }
  const audio::Status valid = config.validate();
  if (!valid.ok()) return audio::Result<RuntimeConfig>(valid);
  return audio::Result<RuntimeConfig>(std::move(config));
}

}  // namespace rootlink::voice
