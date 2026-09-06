#include "rootlink/voice/python_persona.h"
#include <chrono>
#include <cerrno>
#if !defined(_WIN32)
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>
extern char** environ;
#endif

namespace rootlink::voice {
namespace {
using audio::AudioError;
using audio::Status;
using Result = audio::Result<std::string>;
using J = JsonValue;
constexpr std::size_t limit = 2U * 1024U * 1024U;
}

void PythonPersonaProvider::terminate() noexcept {
#if !defined(_WIN32)
  if (input_ >= 0) close(input_);
  if (pid_ > 0) {
    if (waitpid(pid_, nullptr, WNOHANG) == 0) {
      kill(pid_, SIGKILL);
      while (waitpid(pid_, nullptr, 0) < 0 && errno == EINTR) {}
    }
  }
#endif
  input_ = output_ = pid_ = -1;
  pending_.clear();
}

PythonPersonaProvider::~PythonPersonaProvider() {
  if (pid_ > 0 && !cancelled_)
    (void)exchange({{"op", J(std::string("shutdown"))}}, 1000, "done", {}, {});
  terminate();
}

audio::Status PythonPersonaProvider::start(const StopRequested& stopped) {
  if (pid_ > 0) return {};
  if (attempted_) return {AudioError::kClosed, "Python core stopped; restart application"};
  attempted_ = true;
#if defined(_WIN32)
  (void)stopped;
  return {AudioError::kConfigError, "Python backend requires WSL/Linux"};
#else
  int sockets[2];
  if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, sockets) != 0)
    return {AudioError::kIoError, "Cannot create Python IPC"};
  posix_spawn_file_actions_t actions;
  posix_spawn_file_actions_init(&actions);
  posix_spawn_file_actions_adddup2(&actions, sockets[1], STDIN_FILENO);
  posix_spawn_file_actions_adddup2(&actions, sockets[1], STDOUT_FILENO);
  posix_spawn_file_actions_addclose(&actions, sockets[0]);
  posix_spawn_file_actions_addclose(&actions, sockets[1]);
  // Executable and entry are separate argv values. Never invoke a shell.
  char* argv[] = {const_cast<char*>(config_.python_executable.c_str()),
                 const_cast<char*>("-u"), const_cast<char*>(config_.python_core_entry.c_str()), nullptr};
  pid_t child;
  const int result = posix_spawn(&child, argv[0], &actions, nullptr, argv, environ);
  posix_spawn_file_actions_destroy(&actions);
  close(sockets[1]);
  if (result != 0) { close(sockets[0]); return {AudioError::kConfigError, "Cannot launch Python executable/entry"}; }
  pid_ = child;
  input_ = output_ = sockets[0];
  if (fcntl(input_, F_SETFL, O_NONBLOCK) < 0) { terminate(); return {AudioError::kIoError, "Cannot configure IPC"}; }
  J::Object headers;
  for (const auto& item : config_.llm.headers) headers.emplace(item.first, J(item.second));
  J::Object model{{"name", J(config_.llm.model)}, {"provider", J(config_.llm.name)},
      {"api_key", J(config_.llm.api_key)}, {"base_url", J(config_.llm.base_url)},
      {"auth_header", J(config_.llm.auth_header)}, {"headers", J(headers)},
      {"chat_path", J(config_.llm.chat_path)}};
  J::Object settings{{"model", J(model)}, {"data_dir", J(config_.python_data_dir)},
      {"role_dir", J(config_.role_dir)}, {"llm_timeout_ms", J(double(config_.llm_timeout_ms))}};
  return exchange({{"op", J(std::string("init"))}, {"settings", J(settings)}},
      config_.persona_start_timeout_ms, "ready", {}, stopped).status();
#endif
}

audio::Status PythonPersonaProvider::health() {
  if (pid_ <= 0) return {AudioError::kClosed, "Python core unavailable"};
  return exchange({{"op", J(std::string("health"))}}, config_.persona_start_timeout_ms,
                  "ready", {}, {}).status();
}

audio::Result<std::string> PythonPersonaProvider::complete(const std::vector<ChatMessage>& messages,
    const TextDelta& on_delta, const StopRequested& stopped) {
  if (messages.size() != 1 || messages.front().role != "user" || messages.front().content.empty())
    return Result(Status(AudioError::kInvalidArgument, "Python backend accepts one user message"));
  auto status = start(stopped);
  if (!status.ok()) return Result(status);
  return exchange({{"op", J(std::string("message"))}, {"text", J(messages.front().content)}},
                  config_.persona_turn_timeout_ms, "done", on_delta, stopped);
}

audio::Result<std::string> PythonPersonaProvider::exchange(J::Object request, long timeout,
    const std::string& terminal, const TextDelta& delta, const StopRequested& stopped) {
  auto fail = [&](AudioError code, const char* message) { terminate(); return Result(Status(code, message)); };
#if defined(_WIN32)
  (void)request; (void)timeout; (void)terminal; (void)delta; (void)stopped;
  return fail(AudioError::kConfigError, "Python backend requires WSL/Linux");
#else
  if (pid_ <= 0) return fail(AudioError::kClosed, "Python core unavailable");
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout);
  request.emplace("v", J(1.0));
  request.emplace("id", J(double(++id_)));
  const bool message = request.at("op").stringOr() == "message";
  const std::string frame = J(std::move(request)).dump() + "\n";
  if (frame.size() > limit) return fail(AudioError::kInvalidArgument, "Python request exceeds limit");
  std::size_t written = 0, deltas = 0;
  while (true) {
    if (cancelled_ || (stopped && stopped())) return fail(AudioError::kCancelled, "Python operation cancelled; not replayed");
    if (std::chrono::steady_clock::now() >= deadline) return fail(AudioError::kTimeout, "Python operation timed out; not replayed");
    const auto newline = pending_.find('\n');
    if (newline != std::string::npos) {
      auto parsed = J::parse(pending_.substr(0, newline));
      pending_.erase(0, newline + 1);
      if (!parsed.ok()) return fail(AudioError::kProviderError, "Invalid Python JSON protocol");
      const auto& obj = parsed.value();
      const auto* v = obj.find("v"); const auto* id = obj.find("id"); const auto* event = obj.find("event");
      if (!v || v->numberOr() != 1 || !id || id->numberOr() != id_ || !event)
        return fail(AudioError::kProviderError, "Invalid Python protocol version/ID");
      const auto name = event->stringOr();
      const auto* text = obj.find("text");
      if (name == "delta" && message && text && !text->stringOr().empty()) {
        deltas += text->stringOr().size();
        if (deltas > limit) return fail(AudioError::kProviderError, "Python response exceeds limit");
        if (delta) delta(text->stringOr());
      } else if (name == terminal && (!message || (text && !text->stringOr().empty()))) {
        if (!pending_.empty()) return fail(AudioError::kProviderError, "Unexpected Python protocol frame");
        return Result(text ? text->stringOr() : std::string());
      } else return fail(AudioError::kProviderError, "Python core/protocol failed; not replayed");
      continue;
    }
    pollfd descriptor{input_, short(written < frame.size() ? POLLOUT : POLLIN), 0};
    const int ready = poll(&descriptor, 1, 50);
    if (ready < 0 && errno == EINTR) continue;
    if (ready < 0) return fail(AudioError::kIoError, "Python IPC poll failed");
    if (ready == 0) continue;
    if (written < frame.size() && (descriptor.revents & POLLOUT)) {
      const auto count = send(input_, frame.data() + written, frame.size() - written, MSG_NOSIGNAL);
      if (count > 0) written += static_cast<std::size_t>(count);
      else if (errno != EAGAIN && errno != EINTR) return fail(AudioError::kClosed, "Python core exited");
    } else if (descriptor.revents & POLLIN) {
      char buffer[4096];
      const auto count = recv(output_, buffer, sizeof(buffer), 0);
      if (count == 0) return fail(AudioError::kClosed, "Python core exited; not replayed");
      if (count > 0) pending_.append(buffer, static_cast<std::size_t>(count));
      else if (errno != EAGAIN && errno != EINTR) return fail(AudioError::kIoError, "Python IPC read failed");
      if (pending_.size() > limit) return fail(AudioError::kProviderError, "Python response exceeds limit");
    } else if (descriptor.revents & (POLLERR | POLLHUP | POLLNVAL))
      return fail(AudioError::kClosed, "Python core exited; not replayed");
  }
#endif
}
}
