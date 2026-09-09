#include "rootlink/ui/main_view.h"
#include "rootlink/ui/dialogue.h"
#include <iostream>

namespace {
bool expect(bool condition, const char* message) {
  if (!condition) std::cerr << message << '\n';
  return condition;
}
}

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
  states.reset();
  if (states.read() != DisplayState::Idle) return 3;
  states.publish(VoiceState::kListening);
  if (states.read() != DisplayState::Listening) return 4;

  rootlink::ui::DialogueMailbox dialogue;
  rootlink::ui::DialogueSnapshot snapshot;
  std::uint64_t revision = 0;
  if (!expect(dialogue.readIfChanged(revision, snapshot) && snapshot.text.empty(),
              "new dialogue mailbox was not empty")) return 5;

  // A Chinese scalar can arrive in separate stream chunks and must not display
  // an incomplete byte sequence.  It remains one visible character per tick.
  rootlink::ui::DialogueTypewriter writer(50);
  dialogue.beginTurn();
  dialogue.append("\xe4\xbd");
  dialogue.readIfChanged(revision, snapshot);
  writer.update(snapshot, 0);
  if (!expect(!writer.tick(0) && writer.visible().empty(),
              "incomplete UTF-8 was displayed")) return 6;
  dialogue.append("\xa0\xe5\xa5\xbd"); // 你好, split before the first scalar completed.
  dialogue.readIfChanged(revision, snapshot);
  writer.update(snapshot, 1);
  if (!expect(writer.tick(1) && writer.visible() == "\xe4\xbd\xa0",
              "completed Chinese scalar was not displayed once")) return 7;
  if (!expect(!writer.tick(50) && writer.visible() == "\xe4\xbd\xa0",
              "typewriter advanced before 50ms")) return 8;
  if (!expect(writer.tick(51) && writer.visible() == "\xe4\xbd\xa0\xe5\xa5\xbd",
              "second Chinese scalar did not respect cadence")) return 9;

  // Bad source bytes have a stable visible replacement and do not hide the
  // following valid content.
  writer.clear(100);
  writer.update({snapshot.generation, std::string("\xe4") + "A" + "\x80"}, 100);
  if (!expect(writer.tick(100) && writer.visible() == "\xef\xbf\xbd",
              "invalid UTF-8 was not replaced")) return 10;
  if (!expect(writer.tick(150) && writer.visible() == std::string("\xef\xbf\xbd") + "A",
              "valid content after invalid UTF-8 was lost")) return 11;

  // While the model is silent the display clock catches up to now.  A response
  // arriving much later begins with one character instead of a full burst.
  rootlink::ui::DialogueTypewriter delayed(50);
  delayed.update({42, ""}, 0);
  delayed.tick(0);
  delayed.tick(60000);
  delayed.update({42, "abcdef"}, 60000);
  if (!expect(delayed.tick(60000) && delayed.visible() == "a",
              "delayed answer burst into the dialogue")) return 12;
  if (!expect(!delayed.tick(60049) && delayed.visible() == "a",
              "delayed answer ignored the configured interval")) return 13;
  if (!expect(delayed.tick(60050) && delayed.visible() == "ab",
              "delayed answer did not continue at its interval")) return 14;

  // A new reply must replace the previous reply even where their prefixes are
  // identical, so reset/retry cannot leave stale lower-dialogue characters.
  rootlink::ui::DialogueTypewriter generation_writer(50);
  generation_writer.update({7, "\xe7\x94\xb2\xe4\xb9\x99"}, 0); // 甲乙
  generation_writer.tick(0);
  generation_writer.tick(50);
  generation_writer.update({8, "\xe7\x94\xb2\xe4\xb8\x99"}, 100); // 甲丙
  generation_writer.tick(100);
  if (!expect(generation_writer.visible() == "\xe7\x94\xb2",
              "new generation retained an old same-prefix suffix")) return 15;

  // Providers which only supply a final answer (or correct streamed text) use
  // the same turn.  The UI must replace, rather than append to, the draft.
  rootlink::ui::DialogueMailbox final_dialogue;
  rootlink::ui::DialogueTypewriter final_writer(50);
  std::uint64_t final_revision = 0;
  final_dialogue.beginTurn();
  final_dialogue.append("draft");
  final_dialogue.readIfChanged(final_revision, snapshot);
  final_writer.update(snapshot, 0);
  final_writer.tick(0);
  final_dialogue.replace("final");
  final_dialogue.readIfChanged(final_revision, snapshot);
  final_writer.update(snapshot, 50);
  final_writer.tick(50);
  if (!expect(final_writer.visible() == "f",
              "final-only answer did not replace streamed draft")) return 16;

  dialogue.beginTurn();
  dialogue.append(std::string(rootlink::ui::DialogueMailbox::kMaxBytes, 'x'));
  dialogue.append("overflow");
  if (!expect(dialogue.readIfChanged(revision, snapshot) &&
                  snapshot.text.size() == rootlink::ui::DialogueMailbox::kMaxBytes,
              "dialogue mailbox did not enforce its 32768-byte bound")) return 17;
  if (!expect(!dialogue.readIfChanged(revision, snapshot),
              "discarded overflow published another visible update")) return 18;

  dialogue.replace("final");
  if (!expect(dialogue.readIfChanged(revision, snapshot) && snapshot.text == "final",
              "final answer did not replace streamed dialogue")) return 19;
  dialogue.replace(std::string(rootlink::ui::DialogueMailbox::kMaxBytes + 1, 'z'));
  if (!expect(dialogue.readIfChanged(revision, snapshot) &&
                  snapshot.text.size() == rootlink::ui::DialogueMailbox::kMaxBytes,
              "final answer replacement exceeded mailbox bound")) return 20;

  generation_writer.clear(200);
  if (!expect(generation_writer.visible().empty(), "reset did not clear dialogue immediately")) return 21;
  std::cout << "UI mapping, transitions and error latch passed\n";
}
