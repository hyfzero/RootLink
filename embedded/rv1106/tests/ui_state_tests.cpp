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

  // A layout callback owns the actual font/wrapping decision.  With this
  // fixed three-scalar page stand-in, the typewriter must retain every byte,
  // hold a full page, and then reveal exactly one next-page scalar per tick.
  rootlink::ui::DialogueTypewriter paged(50);
  paged.setPageLayout([](const std::string& text) { return text.size() <= 3; }, 200);
  paged.update({91, "abcdefghi"}, 0);
  if (!expect(paged.tick(0) && paged.visible() == "a", "first page did not begin")) return 17;
  if (!expect(paged.tick(50) && paged.tick(100) && paged.visible() == "abc",
              "first page was not filled one scalar at a time")) return 18;
  if (!expect(!paged.tick(150) && paged.visible() == "abc",
              "typewriter turned the page before the hold")) return 19;
  if (!expect(!paged.tick(349) && paged.visible() == "abc",
              "full page changed before its hold expired")) return 20;
  if (!expect(paged.tick(350) && paged.visible() == "d",
              "second page did not start with its pending character")) return 21;
  if (!expect(!paged.tick(399) && paged.visible() == "d",
              "next page ignored normal typing cadence")) return 22;
  if (!expect(paged.tick(400) && paged.tick(450) && paged.visible() == "def",
              "second page lost characters")) return 23;
  if (!expect(!paged.tick(500) && paged.visible() == "def",
              "second page did not enter its hold when full")) return 24;
  // Arriving far after the second hold must clear once and reveal one scalar,
  // never consume a whole page in a catch-up burst.
  if (!expect(paged.tick(1000) && paged.visible() == "g",
              "page transition burst or lost its next character")) return 25;
  if (!expect(paged.tick(1050) && paged.tick(1100) && paged.visible() == "ghi",
              "third page did not contain the remaining characters")) return 26;
  if (!expect(!paged.tick(60000) && paged.visible() == "ghi",
              "final full page was cleared without a following character")) return 27;

  // A generation change (including reset/retry) cancels the old page hold and
  // starts the new answer immediately.  A leading newline after a page break
  // is consumed at the break, so it cannot create a blank new page.
  rootlink::ui::DialogueTypewriter reset_paged(50);
  reset_paged.setPageLayout([](const std::string& text) { return text.size() <= 2; }, 200);
  reset_paged.update({101, "abc"}, 0);
  reset_paged.tick(0);
  reset_paged.tick(50);
  reset_paged.tick(100);  // waits on c until 300ms
  reset_paged.update({102, "XY"}, 101);
  if (!expect(reset_paged.tick(101) && reset_paged.visible() == "X",
              "new generation retained the old page wait")) return 28;
  reset_paged.clear(102);
  reset_paged.update({102, "Z"}, 102);
  if (!expect(reset_paged.tick(102) && reset_paged.visible() == "Z",
              "reset did not cancel the pending page wait")) return 29;

  rootlink::ui::DialogueTypewriter newline_paged(50);
  newline_paged.setPageLayout([](const std::string& text) { return text.size() <= 2; }, 200);
  newline_paged.update({103, "ab\nc"}, 0);
  newline_paged.tick(0);
  newline_paged.tick(50);
  if (!expect(!newline_paged.tick(100) && newline_paged.visible() == "ab",
              "newline triggered a page break too early")) return 30;
  if (!expect(newline_paged.tick(300) && newline_paged.visible() == "c",
              "cross-page newline created a blank page or lost content")) return 31;

  dialogue.beginTurn();
  dialogue.append(std::string(rootlink::ui::DialogueMailbox::kMaxBytes, 'x'));
  dialogue.append("overflow");
  if (!expect(dialogue.readIfChanged(revision, snapshot) &&
                  snapshot.text.size() == rootlink::ui::DialogueMailbox::kMaxBytes,
              "dialogue mailbox did not enforce its 32768-byte bound")) return 32;
  if (!expect(!dialogue.readIfChanged(revision, snapshot),
              "discarded overflow published another visible update")) return 33;

  dialogue.replace("final");
  if (!expect(dialogue.readIfChanged(revision, snapshot) && snapshot.text == "final",
              "final answer did not replace streamed dialogue")) return 34;
  dialogue.replace(std::string(rootlink::ui::DialogueMailbox::kMaxBytes + 1, 'z'));
  if (!expect(dialogue.readIfChanged(revision, snapshot) &&
                  snapshot.text.size() == rootlink::ui::DialogueMailbox::kMaxBytes,
              "final answer replacement exceeded mailbox bound")) return 35;

  generation_writer.clear(200);
  if (!expect(generation_writer.visible().empty(), "reset did not clear dialogue immediately")) return 36;

  // Speech subtitles stay empty until a real playback notification. Cadence
  // uses PCM duration / Unicode scalar count, and cannot complete early.
  rootlink::ui::SpeechMailbox speech;
  rootlink::ui::SpeechSegmentSnapshot speech_snapshot;
  std::uint64_t speech_revision = 0;
  rootlink::ui::SpeechTypewriter subtitles;
  subtitles.setPageLayout([](const std::string&) { return true; }, 200);
  if (!expect(!speech.readFrontIfChanged(speech_revision, speech_snapshot) ||
                  speech_snapshot.generation == 0, "subtitle appeared before playback")) return 37;
  speech.publish("\xe4\xbd\xa0\xe5\xa5\xbd", 1000, 100); // 你好
  speech.readFrontIfChanged(speech_revision, speech_snapshot);
  subtitles.begin(speech_snapshot);
  subtitles.tick(99);
  if (!expect(subtitles.visible().empty(), "subtitle typed before playback start")) return 38;
  subtitles.tick(100);
  if (!expect(subtitles.visible() == "\xe4\xbd\xa0" && !subtitles.complete(),
              "first Unicode scalar did not follow the playback clock")) return 39;
  subtitles.tick(599);
  if (!expect(subtitles.visible() == "\xe4\xbd\xa0", "subtitle cadence ignored PCM duration")) return 40;
  subtitles.tick(600);
  if (!expect(subtitles.visible() == "\xe4\xbd\xa0\xe5\xa5\xbd" && !subtitles.complete(),
              "second scalar appeared at the wrong duration-derived cadence")) return 41;
  subtitles.tick(1100);
  if (!expect(subtitles.complete(), "long PCM duration acknowledged too early")) return 42;
  speech.acknowledge(speech_snapshot.generation);
  if (!expect(speech.consumeFrontAcknowledgement(), "completed subtitle did not acknowledge playback")) return 43;

  // An acknowledgement for an old entry cannot consume a prefetched newer
  // entry, and reset invalidates all pending display work.
  speech.publish("A", 1, 0);
  speech.readFrontIfChanged(speech_revision, speech_snapshot);
  const auto old_generation = speech_snapshot.generation;
  speech.publish("B", 1, 0);
  speech.acknowledge(old_generation + 1);
  if (!expect(!speech.consumeFrontAcknowledgement(), "new-generation ack released old subtitle")) return 44;
  speech.acknowledge(old_generation);
  if (!expect(speech.consumeFrontAcknowledgement(), "current subtitle ack was not accepted")) return 45;
  speech.reset();
  if (!expect(speech.readFrontIfChanged(speech_revision, speech_snapshot) &&
                  speech_snapshot.generation == 0 && speech_snapshot.reset_epoch != 0,
              "reset retained pending subtitle")) return 46;

  // A real layout callback can discover a three-line overflow late. The page
  // remains held before the next scalar and completion follows the final page.
  rootlink::ui::SpeechTypewriter speech_paged;
  speech_paged.setPageLayout([](const std::string& value) { return value.size() <= 3; }, 200);
  speech_paged.begin({700, 0, "abcd", 100, 0});
  speech_paged.tick(0);
  speech_paged.tick(30);
  speech_paged.tick(60);
  speech_paged.tick(90);
  if (!expect(speech_paged.visible() == "abc" && !speech_paged.complete(),
              "three-line overflow did not defer the next subtitle page")) return 47;
  speech_paged.tick(289);
  if (!expect(speech_paged.visible() == "abc", "subtitle page cleared before hold elapsed")) return 48;
  speech_paged.tick(290);
  if (!expect(speech_paged.visible() == "d" && !speech_paged.complete(),
              "page hold was not deducted from the subtitle clock")) return 49;
  speech_paged.tick(300);
  if (!expect(speech_paged.complete(), "subtitle did not finish after the deferred page")) return 50;

  rootlink::ui::SpeechTypewriter newline_speech_paged;
  newline_speech_paged.setPageLayout([](const std::string& value) { return value.size() <= 2; }, 200);
  newline_speech_paged.begin({701, 0, "ab\nc", 100, 0});
  newline_speech_paged.tick(0);
  newline_speech_paged.tick(50);  // b fills page; newline becomes the separator.
  newline_speech_paged.tick(250);
  newline_speech_paged.tick(275);
  if (!expect(newline_speech_paged.visible() == "c",
              "cross-page newline created a blank subtitle page")) return 51;

  // Real UTF-8 Chinese plus explicit page-boundary newlines: each page holds
  // exactly three glyphs, and the two consumed newlines still count toward
  // the segment's Unicode schedule.
  rootlink::ui::SpeechTypewriter chinese_pages;
  chinese_pages.setPageLayout([](const std::string& value) { return value.size() <= 9; }, 200);
  chinese_pages.begin({702, 0, u8"甲乙丙\n丁戊己\n庚", 0, 0});
  chinese_pages.tick(0);
  if (!expect(chinese_pages.visible() == u8"甲乙丙", "first Chinese subtitle page was wrong")) return 52;
  chinese_pages.tick(200);
  if (!expect(chinese_pages.visible() == u8"丁戊己", "second Chinese subtitle page was blank or wrong")) return 53;
  chinese_pages.tick(400);
  if (!expect(chinese_pages.visible() == u8"庚" && chinese_pages.complete(),
              "third Chinese subtitle page did not complete")) return 54;
  std::cout << "UI mapping, transitions and error latch passed\n";
}
