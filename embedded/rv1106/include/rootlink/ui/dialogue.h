#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <string>
#include <utility>
#include <functional>

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
}
