#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <string>
#include <utility>
#include <functional>
#include <deque>

namespace rootlink::ui {
struct DialogueSnapshot {
  std::uint64_t generation{0};
  std::string text;
};

// Voice worker writes; the UI copies only when content changes. Never hold this
// mutex while calling LVGL or a provider. The cap bounds a runaway answer stream.
class DialogueMailbox {
 public:
  static constexpr std::size_t kMaxBytes = 32768;
  void beginTurn() {
    std::lock_guard<std::mutex> lock(mutex_);
    ++value_.generation;
    value_.text.clear();
    ++revision_;
  }
  void append(const std::string& delta) {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto count = std::min(delta.size(), kMaxBytes - value_.text.size());
    if (count) { value_.text.append(delta, 0, count); ++revision_; }
  }
  // A final answer may differ from its streamed deltas.  Keep the turn, but
  // publish the final bounded text as a new mailbox revision.
  void replace(std::string text) {
    if (text.size() > kMaxBytes) text.resize(kMaxBytes);
    std::lock_guard<std::mutex> lock(mutex_);
    value_.text = std::move(text);
    ++revision_;
  }
  bool readIfChanged(std::uint64_t& seen, DialogueSnapshot& value) const {
    std::lock_guard<std::mutex> lock(mutex_);
    if (seen == revision_) return false;
    value = value_;
    seen = revision_;
    return true;
  }
 private:
  mutable std::mutex mutex_;
  DialogueSnapshot value_;
  std::uint64_t revision_{1};
};

// Deterministic clock supplied by the main thread; one Unicode scalar per step,
// including punctuation. Incomplete UTF-8 stays pending until the next delta.
class DialogueTypewriter {
 public:
  explicit DialogueTypewriter(unsigned interval_ms = 50)
      : interval_ms_(std::max(1U, interval_ms)) {}
  // The view measures with its real font and wrapping width; no byte/character
  // count approximation for Chinese, Latin words or explicit newlines.
  void setPageLayout(std::function<bool(const std::string&)> fits, unsigned hold_ms) {
    fits_page_ = std::move(fits);
    page_hold_ms_ = hold_ms;
  }
  void update(const DialogueSnapshot& value, std::uint64_t now_ms) {
    if (value.generation != generation_ ||
        value.text.compare(0, target_.size(), target_) != 0) {
      clear(now_ms);
      generation_ = value.generation;
    }
    target_ = value.text;
  }
  void clear(std::uint64_t now_ms) {
    target_.clear(); visible_.clear(); cursor_ = 0; due_ms_ = now_ms;
    awaiting_utf8_ = false;
    page_waiting_ = false;
  }
  bool tick(std::uint64_t now_ms) {
    if (cursor_ == target_.size()) { due_ms_ = std::max(due_ms_, now_ms); return false; }
    if (now_ms < due_ms_) return false;
    if (page_waiting_) {
      if (now_ms < page_due_ms_) return false;
      visible_.clear();
      page_waiting_ = false;
      due_ms_ = now_ms; // Start the next page at normal speed, never catch up.
    }
    const auto budget = std::min<std::uint64_t>(64, 1 + (now_ms - due_ms_) / interval_ms_);
    bool changed = false;
    for (std::uint64_t n = 0; n < budget && cursor_ < target_.size(); ++n) {
      const auto first = static_cast<unsigned char>(target_[cursor_]);
      std::size_t bytes = first < 0x80 ? 1 :
          first >= 0xc2 && first <= 0xdf ? 2 :
          first >= 0xe0 && first <= 0xef ? 3 :
          first >= 0xf0 && first <= 0xf4 ? 4 : 0;
      if (bytes && target_.size() - cursor_ < bytes) {
        awaiting_utf8_ = true;
        due_ms_ = now_ms;
        break;
      }
      // The rest of a split scalar may arrive between UI ticks.  Once it does,
      // reveal it immediately, then start a full interval for the next scalar.
      const bool resumed_split_scalar = awaiting_utf8_;
      if (resumed_split_scalar) {
        due_ms_ = now_ms;
        awaiting_utf8_ = false;
      }
      for (std::size_t i = 1; i < bytes; ++i) {
        const auto c = static_cast<unsigned char>(target_[cursor_ + i]);
        if ((c & 0xc0) != 0x80 || (i == 1 &&
            ((first == 0xe0 && c < 0xa0) || (first == 0xed && c >= 0xa0) ||
             (first == 0xf0 && c < 0x90) || (first == 0xf4 && c >= 0x90)))) {
          bytes = 0; break;
        }
      }
      const std::string scalar = !bytes || first == 0 ? "\xef\xbf\xbd" :
          target_.substr(cursor_, bytes);
      if (!visible_.empty() && fits_page_ && !fits_page_(visible_ + scalar)) {
        page_waiting_ = true;
        page_due_ms_ = now_ms + page_hold_ms_;
        if (scalar == "\n") cursor_ += bytes;
        break; // Keep the scalar for the next page; a newline is the page break.
      }
      visible_ += scalar;
      cursor_ += !bytes || first == 0 ? 1 : bytes;
      changed = true;
      due_ms_ += interval_ms_;
      if (resumed_split_scalar) break;
    }
    if (cursor_ == target_.size()) due_ms_ = now_ms + interval_ms_;
    return changed;
  }
  const std::string& visible() const { return visible_; }
 private:
  unsigned interval_ms_;
  std::uint64_t generation_{0}, due_ms_{0};
  std::size_t cursor_{0};
  bool awaiting_utf8_{false};
  bool page_waiting_{false};
  unsigned page_hold_ms_{2000};
  std::uint64_t page_due_ms_{0};
  std::function<bool(const std::string&)> fits_page_;
  std::string target_, visible_;
};

// A sentence is published only after its PCM has reached the playback device.
// The UI owns the acknowledgement: a stale acknowledgement can never remove a
// newer sentence because each entry has a monotonic generation.
struct SpeechSegmentSnapshot {
  std::uint64_t generation{0};
  std::uint64_t reset_epoch{0};
  std::string text;
  std::uint64_t duration_ms{0};
  std::uint64_t started_ms{0};
};

class SpeechMailbox {
 public:
  void reset() {
    std::lock_guard<std::mutex> lock(mutex_);
    pending_.clear();
    acknowledged_ = 0;
    ++reset_epoch_;
    ++revision_;
  }
  void publish(std::string text, std::uint64_t duration_ms, std::uint64_t started_ms) {
    std::lock_guard<std::mutex> lock(mutex_);
    pending_.push_back({++generation_, reset_epoch_, std::move(text), duration_ms, started_ms});
    ++revision_;
  }
  bool readFrontIfChanged(std::uint64_t& seen, SpeechSegmentSnapshot& value) const {
    std::lock_guard<std::mutex> lock(mutex_);
    if (seen == revision_) return false;
    if (pending_.empty()) value = {};
    else value = pending_.front();
    value.reset_epoch = reset_epoch_;
    seen = revision_;
    return true;
  }
  void acknowledge(std::uint64_t generation) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!pending_.empty() && pending_.front().generation == generation)
      acknowledged_ = generation;
  }
  // Called by the voice worker after drain. It consumes at most the front
  // entry, so an acknowledgement from a prior generation cannot release one
  // that was prefetched later.
  bool consumeFrontAcknowledgement() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (pending_.empty() || acknowledged_ != pending_.front().generation) return false;
    pending_.pop_front();
    acknowledged_ = 0;
    ++revision_;
    return true;
  }
 private:
  mutable std::mutex mutex_;
  std::deque<SpeechSegmentSnapshot> pending_;
  std::uint64_t generation_{0};
  std::uint64_t acknowledged_{0};
  std::uint64_t reset_epoch_{0};
  std::uint64_t revision_{1};
};

// Sentence-local deterministic typewriter. Its cadence is derived from the
// PCM duration and Unicode scalar count. Page holds pause this clock: without
// a predictive layout pass, a late font-wrap adds its hold to the display
// duration, so the runtime waits rather than overwriting unread text.
class SpeechTypewriter {
 public:
  void setPageLayout(std::function<bool(const std::string&)> fits, unsigned hold_ms) {
    fits_page_ = std::move(fits); page_hold_ms_ = hold_ms;
  }
  void begin(const SpeechSegmentSnapshot& segment) {
    generation_ = segment.generation; target_ = segment.text; visible_.clear();
    cursor_ = shown_ = 0; total_ = scalarCount(target_); duration_ms_ = segment.duration_ms;
    started_ms_ = segment.started_ms; last_ms_ = started_ms_; typing_ms_ = 0;
    page_waiting_ = false; completed_ = false;
  }
  void clear() { generation_ = 0; target_.clear(); visible_.clear(); cursor_ = shown_ = total_ = 0;
                 page_waiting_ = completed_ = false; }
  bool active() const { return generation_ != 0; }
  std::uint64_t generation() const { return generation_; }
  bool tick(std::uint64_t now_ms) {
    if (!active() || completed_ || now_ms < started_ms_) return false;
    if (page_waiting_) {
      if (now_ms < page_due_ms_) return false;
      visible_.clear(); page_waiting_ = false; last_ms_ = now_ms;
    }
    typing_ms_ += now_ms - last_ms_;
    last_ms_ = now_ms;
    const auto wanted = duration_ms_ == 0 ? total_ :
        std::min(total_, static_cast<std::size_t>((typing_ms_ * total_) / duration_ms_ + 1));
    bool changed = false;
    while (shown_ < wanted && cursor_ < target_.size()) {
      const auto bytes = scalarBytes(target_, cursor_);
      const auto scalar = target_.substr(cursor_, bytes);
      if (!visible_.empty() && fits_page_ && !fits_page_(visible_ + scalar)) {
        // A newline at an already-full page is the page separator, not the
        // first (blank) line of the next page.
        if (scalar == "\n") { cursor_ += bytes; ++shown_; }
        page_waiting_ = true; page_due_ms_ = now_ms + page_hold_ms_; break;
      }
      visible_ += scalar; cursor_ += bytes; ++shown_; changed = true;
    }
    if (cursor_ == target_.size() && !page_waiting_ &&
        (duration_ms_ == 0 || typing_ms_ >= duration_ms_)) completed_ = true;
    return changed;
  }
  bool complete() const { return completed_; }
  const std::string& visible() const { return visible_; }
 private:
  static std::size_t scalarBytes(const std::string& text, std::size_t offset) {
    const auto first = static_cast<unsigned char>(text[offset]);
    const std::size_t bytes = first < 0x80 ? 1 : first >= 0xc2 && first <= 0xdf ? 2 :
        first >= 0xe0 && first <= 0xef ? 3 : first >= 0xf0 && first <= 0xf4 ? 4 : 1;
    if (offset + bytes > text.size()) return 1;
    for (std::size_t i = 1; i < bytes; ++i)
      if ((static_cast<unsigned char>(text[offset + i]) & 0xc0) != 0x80) return 1;
    return bytes;
  }
  static std::size_t scalarCount(const std::string& text) {
    std::size_t count = 0;
    for (std::size_t offset = 0; offset < text.size(); ++count) offset += scalarBytes(text, offset);
    return count;
  }
  std::function<bool(const std::string&)> fits_page_;
  std::uint64_t generation_{0}, duration_ms_{0}, started_ms_{0}, last_ms_{0},
      typing_ms_{0}, page_due_ms_{0};
  std::size_t cursor_{0}, shown_{0}, total_{0};
  unsigned page_hold_ms_{2000};
  bool page_waiting_{false}, completed_{false};
  std::string target_, visible_;
};
}
