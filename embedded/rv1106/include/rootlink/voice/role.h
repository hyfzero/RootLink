#pragma once

#include <map>
#include <string>
#include <vector>

#include "rootlink/audio/status.h"
#include "rootlink/voice/json_value.h"

namespace rootlink::voice {

struct ChatMessage {
  std::string role;
  std::string content;
  std::size_t token_count{0};
};

struct CompanionRole {
  std::string id{"default"};
  std::string name{"小林"};
  std::string intro{"一个真诚、简洁的语音伙伴"};
  JsonValue profile{JsonValue::Object{}};
  JsonValue state{JsonValue::Object{}};
  JsonValue memories{JsonValue::Object{}};
  JsonValue speaking_style{JsonValue::Object{}};
  JsonValue config{JsonValue::Object{}};
};

/** @brief 读取 RootLink 导出的角色目录；缺失目录时可返回内置最小角色。 */
class RoleRepository {
 public:
  audio::Result<CompanionRole> load(const std::string& role_dir,
                                    bool allow_builtin_fallback = true) const;
};

/** @brief 按 Flutter RootLinkAgentRuntime 的字段顺序构造系统提示词和历史。 */
class PromptBuilder {
 public:
  std::string buildSystemPrompt(const CompanionRole& role) const;
  std::vector<ChatMessage> buildMessages(const CompanionRole& role,
                                         const std::vector<ChatMessage>& history,
                                         const std::string& user_text,
                                         std::size_t max_turns,
                                         std::size_t token_budget) const;
  static std::size_t estimateTokens(const std::string& text) noexcept;
};

/**
 * @brief 每日 JSONL 会话存储。
 *
 * 一行只保存 role/content/token_count，尾部半行会在读取时忽略，因此掉电不会破坏
 * 之前已经完整写入的消息。
 */
class ConversationSession {
 public:
  ConversationSession(std::string session_root, std::string role_id);
  audio::Status append(const ChatMessage& message);
  audio::Result<std::vector<ChatMessage>> loadRecent(std::size_t max_messages) const;
  std::string currentPath() const;

 private:
  std::string session_root_;
  std::string role_id_;
};

}  // namespace rootlink::voice
