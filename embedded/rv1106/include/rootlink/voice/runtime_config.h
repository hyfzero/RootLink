#pragma once

#include <cstddef>
#include <map>
#include <string>
#include <vector>

#include "rootlink/audio/status.h"

namespace rootlink::voice {

/** @brief 固定 20 ms 帧上的门限与切句参数；使用前必须通过 RuntimeConfig::validate。 */
struct VadConfig {
  std::size_t start_frames{3};
  std::size_t pre_roll_ms{400};
  std::size_t end_silence_ms{800};
  std::size_t min_utterance_ms{300};
  std::size_t max_utterance_ms{30000};
  double min_rms{250.0};
  double noise_multiplier{3.0};
  double noise_alpha{0.02};
};

/** @brief OpenAI 兼容供应商设置；密钥仅保存在内存中，不可序列化到日志。 */
struct ProviderConfig {
  std::string name;
  std::string model;
  std::string base_url;
  std::string api_key;
  std::string api_key_env;
  bool auth_header{true};
  std::map<std::string, std::string> headers;
  std::string chat_path{"/chat/completions"};
};

/**
 * @brief Stage 2 统一运行配置。
 *
 * 构建脚本和运行程序读取同一份 KEY=VALUE 文件，但密钥不允许写在该文件中。
 * API 密钥优先取进程环境变量，其次取权限受控的 secrets 文件，最后才兼容读取
 * RootLink models.json 中已有的 api_key。
 */
struct RuntimeConfig {
  std::string target{"simulator"};
  std::string audio_api{"simulated"};
  std::string service_mode{"mock"};
  std::string persona_backend{"simple"};
  std::string ui_backend{"none"};
  std::string ui_device{"/dev/fb0"};
  std::string ui_input_device; // optional Linux evdev touchscreen, e.g. /dev/input/event0
  unsigned ui_width{320};
  unsigned ui_height{240};
  std::string python_executable;
  std::string python_core_entry;
  std::string python_data_dir;
  long persona_start_timeout_ms{30000};
  long persona_turn_timeout_ms{300000};
  std::string capture_device{"default"};
  std::string playback_device{"default"};
  std::size_t buffer_frames{100};

  ProviderConfig asr{"dashscope", "qwen3-asr-flash",
                     "https://dashscope.aliyuncs.com/compatible-mode/v1", {},
                     "DASHSCOPE_API_KEY", true, {}};
  ProviderConfig llm{"qwen", "qwen-plus",
                     "https://dashscope.aliyuncs.com/compatible-mode/v1", {},
                     "DASHSCOPE_API_KEY", true, {}};
  ProviderConfig tts{"dashscope", "cosyvoice-v3-flash",
                     "https://dashscope.aliyuncs.com/api/v1", {},
                     "DASHSCOPE_API_KEY", true, {}};
  std::string tts_voice{"longanyang"};
  unsigned tts_sample_rate{16000};
  std::string tts_translate_to{"none"};

  std::string models_file{"/data/rootlink/config/models.json"};
  std::string secrets_file{"/etc/rootlink/rootlink-secrets.env"};
  std::string role_dir{"/data/rootlink/roles/default"};
  std::string session_dir{"/data/rootlink/sessions"};
  std::size_t history_turns{8};
  std::size_t history_token_budget{12000};
  VadConfig vad;

  long connect_timeout_ms{5000};
  long asr_timeout_ms{45000};
  long llm_timeout_ms{60000};
  long tts_timeout_ms{45000};
  long tts_translation_timeout_ms{60000};
  std::size_t retry_count{1};
  std::size_t max_json_bytes{2U * 1024U * 1024U};
  std::size_t max_tts_bytes{8U * 1024U * 1024U};
  std::vector<std::string> warnings;

  audio::Status validate() const;
};

audio::Result<RuntimeConfig> loadRuntimeConfig(const std::string& path);

}  // namespace rootlink::voice
