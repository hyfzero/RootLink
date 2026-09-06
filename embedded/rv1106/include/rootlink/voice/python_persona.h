#pragma once
#include "rootlink/voice/providers.h"
#include "rootlink/voice/json_value.h"

namespace rootlink::voice {
// One serial session, owned by the caller thread. cancel() is safe from another thread.
class PythonPersonaProvider final : public LlmProvider {
 public:
  explicit PythonPersonaProvider(RuntimeConfig config) : config_(std::move(config)) {}
  ~PythonPersonaProvider() override;
  audio::Status start(const StopRequested& stopped = {});
  audio::Status health();
  audio::Result<std::string> complete(const std::vector<ChatMessage>& messages,
      const TextDelta& on_delta, const StopRequested& stopped) override;
  void cancel() noexcept override { cancelled_.store(true); }
 private:
  audio::Result<std::string> exchange(JsonValue::Object request, long timeout,
      const std::string& terminal, const TextDelta& delta, const StopRequested& stopped);
  void terminate() noexcept;
  RuntimeConfig config_;
  int pid_{-1}, input_{-1}, output_{-1};
  unsigned id_{0};
  bool attempted_{false};
  std::string pending_;
  std::atomic<bool> cancelled_{false};
};
}
