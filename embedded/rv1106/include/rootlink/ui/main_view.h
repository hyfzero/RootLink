#pragma once
#include <atomic>
#include <memory>
#include <string>
#include "rootlink/voice/voice_runtime.h"

namespace rootlink::ui {
enum class DisplayState { Idle, Listening, Thinking, Speaking, Error };
inline DisplayState displayState(voice::VoiceState state) noexcept {
  switch (state) {
    case voice::VoiceState::kListening: return DisplayState::Listening;
    case voice::VoiceState::kTranscribing:
    case voice::VoiceState::kThinking:
    case voice::VoiceState::kSynthesizing: return DisplayState::Thinking;
    case voice::VoiceState::kPlaying: return DisplayState::Speaking;
    case voice::VoiceState::kError: return DisplayState::Error;
    default: return DisplayState::Idle;
  }
}
// One producer; errors remain visible while the runtime releases its resources.
class StateMailbox {
 public:
  void publish(voice::VoiceState state) noexcept {
    if (state_.load() != DisplayState::Error) state_.store(displayState(state));
  }
  DisplayState read() const noexcept { return state_.load(); }
  // Only call after the old producer has been joined.
  void reset() noexcept { state_.store(DisplayState::Idle); }
 private:
  std::atomic<DisplayState> state_{DisplayState::Idle};
};

// All methods, including destruction, belong to the UI/main thread.
class MainView {
 public:
  MainView();
  ~MainView();
  audio::Status initialize(const voice::RuntimeConfig& config);
  bool tick(DisplayState state); // false: window closed
  // Updates only the already-revealed dialogue text. Call on the UI thread.
  void setDialogue(const std::string& text);
  bool dialogueFits(const std::string& text) const;
  bool takeResetRequest(); // coalesces clicks; does not touch voice resources
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
