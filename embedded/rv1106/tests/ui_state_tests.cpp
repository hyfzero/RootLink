#include "rootlink/ui/main_view.h"
#include <iostream>
int main() {
  using rootlink::voice::VoiceState;
  using rootlink::ui::DisplayState;
  using rootlink::ui::displayState;
  const bool mapped = displayState(VoiceState::kListening) == DisplayState::Listening &&
      displayState(VoiceState::kTranscribing) == DisplayState::Thinking &&
      displayState(VoiceState::kThinking) == DisplayState::Thinking &&
      displayState(VoiceState::kSynthesizing) == DisplayState::Thinking &&
      displayState(VoiceState::kPlaying) == DisplayState::Speaking &&
      displayState(VoiceState::kStopping) == DisplayState::Idle;
  rootlink::ui::StateMailbox states;
  for (int n = 0; n < 10000; ++n) {
    states.publish(VoiceState::kListening);
    states.publish(VoiceState::kPlaying);
  }
  if (!mapped || states.read() != DisplayState::Speaking) return 1;
  states.publish(VoiceState::kError);
  states.publish(VoiceState::kStopping);
  states.publish(VoiceState::kIdle);
  if (states.read() != DisplayState::Error) return 2;
  std::cout << "UI mapping, transitions and error latch passed\n";
}
