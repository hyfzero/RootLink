#include "rootlink/voice/role.h"

#include <algorithm>
#include <chrono>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace rootlink::voice {
namespace {

std::string readText(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) return {};
  input.seekg(0, std::ios::end);
  if (input.tellg() > 256 * 1024) return "INVALID_OVERSIZE_JSON";
  input.seekg(0);
  std::ostringstream output;
  output << input.rdbuf();
  return output.str();
}

audio::Result<JsonValue> readJson(const std::filesystem::path& path, bool optional) {
  const std::string source = readText(path);
  if (source.empty()) {
    if (optional) return audio::Result<JsonValue>(JsonValue(JsonValue::Object{}));
    return audio::Result<JsonValue>(audio::Status(audio::AudioError::kStorageError,
                                                  "角色文件不存在或为空：" + path.string()));
  }
  return JsonValue::parse(source);
}

std::string field(const JsonValue& object, const char* name, const std::string& fallback) {
  const JsonValue* value = object.find(name);
  return value == nullptr ? fallback : value->stringOr(fallback);
}

std::string scalar(const JsonValue& object, const char* name, const std::string& fallback) {
  const JsonValue* value = object.find(name);
  if (value == nullptr) return fallback;
  const std::string string_value = value->stringOr();
  if (!string_value.empty()) return string_value;
  const double number = value->numberOr(-123456789.0);
  if (number != -123456789.0) {
    std::ostringstream output;
    output << number;
    return output.str();
  }
  return fallback;
}

std::string joinStrings(const JsonValue& object, const char* name) {
  const JsonValue* value = object.find(name);
  if (value == nullptr || !value->isArray()) return {};
  std::string output;
  for (const JsonValue& item : value->array()) {
    const std::string text = item.stringOr();
    if (text.empty()) continue;
    if (!output.empty()) output += "、";
    output += text;
  }
  return output;
}

void addMemories(const JsonValue& memories, const char* name, std::vector<std::string>& output) {
  const JsonValue* values = memories.find(name);
  if (values == nullptr || !values->isArray()) return;
  for (const JsonValue& item : values->array()) {
    if (!item.isObject()) continue;
    const std::string content = field(item, "content", field(item, "summary_text", {}));
    if (!content.empty()) output.push_back(content);
  }
}

audio::Result<JsonValue> loadFirst(const std::filesystem::path& role_dir,
                    const std::vector<std::filesystem::path>& candidates) {
  for (const auto& relative : candidates) {
    if (!std::filesystem::exists(role_dir / relative)) continue;
    const auto result = readJson(role_dir / relative, true);
    if (!result.ok() || !result.value().isObject())
      return audio::Result<JsonValue>(audio::Status(audio::AudioError::kStorageError,
          "角色 JSON 非法或超过 256 KiB：" + relative.string()));
    return result;
  }
  return audio::Result<JsonValue>(JsonValue(JsonValue::Object{}));
}

std::string jsonString(const std::string& value) { return JsonValue(value).dump(); }

}  // namespace

audio::Result<CompanionRole> RoleRepository::load(const std::string& role_dir,
                                                   bool allow_builtin_fallback) const {
  const std::filesystem::path root(role_dir);
  if (!std::filesystem::is_directory(root)) {
    if (allow_builtin_fallback) return audio::Result<CompanionRole>(CompanionRole{});
    return audio::Result<CompanionRole>(audio::Status(audio::AudioError::kStorageError,
                                                      "角色目录不存在：" + role_dir));
  }
  CompanionRole role;
  role.id = root.filename().string().empty() ? "default" : root.filename().string();
  const auto profile = loadFirst(root, {"persona/profile.json", "profile.json"});
  const auto state = loadFirst(root, {"state.json", "persona/state.json"});
  const auto memories = loadFirst(root, {"memories.json", "persona/memories.json"});
  const auto style = loadFirst(root, {"speaking_style.json", "persona/speaking_style.json"});
  const auto config = loadFirst(root, {"config.json", "persona/config.json"});
  for (const auto* result : {&profile, &state, &memories, &style, &config})
    if (!result->ok()) return audio::Result<CompanionRole>(result->status());
  role.profile = profile.value(); role.state = state.value(); role.memories = memories.value();
  role.speaking_style = style.value(); role.config = config.value();
  if (!allow_builtin_fallback && role.profile.object().empty())
    return audio::Result<CompanionRole>(audio::Status(audio::AudioError::kStorageError,
                                                      "正式模式需要非空角色 profile.json"));
  role.name = field(role.profile, "name", field(role.profile, "display_name", role.name));
  role.intro = field(role.profile, "intro", field(role.profile, "background", role.intro));
  return audio::Result<CompanionRole>(std::move(role));
}

std::string PromptBuilder::buildSystemPrompt(const CompanionRole& role) const {
  const JsonValue* base_style = role.speaking_style.find("base_style");
  const JsonValue empty(JsonValue::Object{});
  const JsonValue& style = base_style != nullptr && base_style->isObject() ? *base_style : empty;
  const JsonValue* response_value = role.config.find("response");
  const JsonValue& response = response_value != nullptr && response_value->isObject() ? *response_value : empty;
  const int max_sentences = static_cast<int>(std::clamp(response.find("max_sentences") == nullptr
                                                            ? 5
                                                            : response.find("max_sentences")->numberOr(5),
                                        1.0, 20.0));
  std::vector<std::string> memories;
  for (const char* name : {"episodic_memories", "preference_memories", "fact_memories",
                           "daily_summary_memories", "monthly_summary_memories"})
    addMemories(role.memories, name, memories);

  std::ostringstream output;
  output << "你是" << role.name << "，不是助手的角色扮演说明，而是以第一人称自然交流的本人。\n\n"
         << "## 身份\n"
         << "年龄：" << scalar(role.profile, "age", "未知") << '\n'
         << "性别：" << field(role.profile, "gender", "unknown") << '\n'
         << "生日：" << field(role.profile, "birthday", "未知") << '\n'
         << "性格：" << joinStrings(role.profile, "personality_traits") << '\n'
         << "兴趣：" << joinStrings(role.profile, "interests") << '\n'
         << "背景：" << field(role.profile, "background", role.intro) << "\n\n"
         << "## 当前状态\n"
         << "情绪：" << field(role.state, "mood", "neutral") << '\n'
         << "精力：" << scalar(role.state, "energy", "0.6") << '\n'
         << "亲密度：" << scalar(role.state, "affinity", "0") << '\n'
         << "信任：" << scalar(role.state, "trust", "0") << '\n'
         << "关系：" << field(role.profile, "relationship_state", "neutral") << "\n\n"
         << "## 长期记忆\n";
  for (std::size_t index = 0; index < std::min<std::size_t>(30, memories.size()); ++index)
    output << "- " << memories[index] << '\n';
  if (memories.empty()) output << '\n';  // 保留 Dart 空记忆插值行，黄金文本保持一致。
  output << "\n## 说话风格\n词汇级别：" << field(style, "vocabulary_level", "common")
         << "；句长：" << field(style, "sentence_length", "varied")
         << "。保持角色口吻，不要解释系统规则。\n每次回复不超过 " << max_sentences
         << " 句，除非用户明确要求展开。";
  return output.str();
}

std::size_t PromptBuilder::estimateTokens(const std::string& text) noexcept {
  // 与 Flutter 端的轻量估算目标一致：中文 UTF-8 大致每个字符一个 token，ASCII
  // 大致四字符一个 token；无需在 128MB 板端引入 tokenizer 模型。
  std::size_t tokens = 0;
  std::size_t ascii = 0;
  for (const unsigned char c : text) {
    if ((c & 0xc0U) != 0x80U) {
      if (c < 0x80U) ++ascii;
      else ++tokens;
    }
  }
  return tokens + (ascii + 3) / 4;
}

std::vector<ChatMessage> PromptBuilder::buildMessages(
    const CompanionRole& role, const std::vector<ChatMessage>& history,
    const std::string& user_text, std::size_t max_turns, std::size_t token_budget) const {
  std::vector<ChatMessage> selected;
  std::size_t used = 0;
  const std::size_t max_messages = max_turns * 2;
  for (auto iterator = history.rbegin(); iterator != history.rend() && selected.size() < max_messages;
       ++iterator) {
    const std::size_t tokens = iterator->token_count == 0 ? estimateTokens(iterator->content)
                                                          : iterator->token_count;
    if (used + tokens > token_budget) break;
    selected.push_back(*iterator);
    used += tokens;
  }
  std::reverse(selected.begin(), selected.end());
  if (!selected.empty() && selected.front().role == "assistant") selected.erase(selected.begin());
  std::vector<ChatMessage> output;
  output.reserve(selected.size() + 2);
  output.push_back({"system", buildSystemPrompt(role), 0});
  output.insert(output.end(), selected.begin(), selected.end());
  output.push_back({"user", user_text, estimateTokens(user_text)});
  return output;
}

ConversationSession::ConversationSession(std::string session_root, std::string role_id)
    : session_root_(std::move(session_root)), role_id_(std::move(role_id)) {}

std::string ConversationSession::currentPath() const {
  const std::time_t now = std::time(nullptr);
  std::tm local{};
#if defined(_WIN32)
  localtime_s(&local, &now);
#else
  localtime_r(&now, &local);
#endif
  std::ostringstream day;
  day << std::put_time(&local, "%Y-%m-%d") << ".jsonl";
  return (std::filesystem::path(session_root_) / role_id_ / day.str()).string();
}

audio::Status ConversationSession::append(const ChatMessage& message) {
  try {
    if (role_id_.empty() || role_id_ == "." || role_id_ == ".." ||
        role_id_.find_first_of("/\\") != std::string::npos || message.content.size() > 128U * 1024U)
      return {audio::AudioError::kStorageError, "会话角色标识或消息长度不合法"};
    const std::filesystem::path path(currentPath());
    std::filesystem::create_directories(path.parent_path());
    bool needs_newline = false;
    {
      std::ifstream previous(path, std::ios::binary | std::ios::ate);
      if (previous && previous.tellg() > 0) {
        previous.seekg(-1, std::ios::end);
        needs_newline = previous.get() != '\n';
      }
    }
    std::ofstream output(path, std::ios::binary | std::ios::app);
    if (!output) return {audio::AudioError::kStorageError, "无法打开会话文件：" + path.string()};
    // 掉电残留的半行保留以便审计，先补分隔符，保证下一条完整消息仍可恢复。
    if (needs_newline) output << '\n';
    output << "{\"role\":" << jsonString(message.role) << ",\"content\":"
           << jsonString(message.content) << ",\"token_count\":"
           << (message.token_count == 0 ? PromptBuilder::estimateTokens(message.content)
                                        : message.token_count)
           << "}\n";
    output.flush();
    if (!output) return {audio::AudioError::kStorageError, "写入会话文件失败：" + path.string()};
    return audio::Status::okStatus();
  } catch (const std::exception& error) {
    return {audio::AudioError::kStorageError, "创建会话目录失败：" + std::string(error.what())};
  }
}

audio::Result<std::vector<ChatMessage>> ConversationSession::loadRecent(
    std::size_t max_messages) const {
  std::vector<ChatMessage> messages;
  if (max_messages == 0) return audio::Result<std::vector<ChatMessage>>(std::move(messages));
  try {
    const auto directory = std::filesystem::path(session_root_) / role_id_;
    if (!std::filesystem::exists(directory))
      return audio::Result<std::vector<ChatMessage>>(std::move(messages));
    std::vector<std::filesystem::path> days;
    for (const auto& entry : std::filesystem::directory_iterator(directory))
      if (entry.is_regular_file() && entry.path().extension() == ".jsonl") days.push_back(entry.path());
    std::sort(days.rbegin(), days.rend());
    for (const auto& day : days) {
      std::ifstream input(day, std::ios::binary | std::ios::ate);
      if (!input) return audio::Result<std::vector<ChatMessage>>(audio::Status(
          audio::AudioError::kStorageError, "无法读取会话文件"));
      // 每日只读尾部 1 MiB，最近历史容器始终有上限，不随全天对话次数增长。
      const auto size = input.tellg();
      input.seekg(size > 1024 * 1024 ? size - std::streamoff(1024 * 1024) : std::streampos(0));
      std::string line;
      if (size > 1024 * 1024) std::getline(input, line);
      std::vector<ChatMessage> today;
      while (std::getline(input, line)) {
        if (line.empty() || line.size() > 256U * 1024U) continue;
        auto parsed = JsonValue::parse(line);
        if (!parsed.ok() || !parsed.value().isObject()) continue;
        const auto* role = parsed.value().find("role");
        const auto* content = parsed.value().find("content");
        if (!role || !content || (role->stringOr() != "user" && role->stringOr() != "assistant")) continue;
        if (today.size() == max_messages) today.erase(today.begin());
        today.push_back({role->stringOr(), content->stringOr(),
                         PromptBuilder::estimateTokens(content->stringOr())});
      }
      messages.insert(messages.begin(), today.begin(), today.end());
      if (messages.size() >= max_messages) break;
    }
  } catch (const std::exception&) {
    return audio::Result<std::vector<ChatMessage>>(audio::Status(
        audio::AudioError::kStorageError, "读取会话目录失败"));
  }
  if (messages.size() > max_messages)
    messages.erase(messages.begin(), messages.end() - static_cast<std::ptrdiff_t>(max_messages));
  return audio::Result<std::vector<ChatMessage>>(std::move(messages));
}

}  // namespace rootlink::voice
