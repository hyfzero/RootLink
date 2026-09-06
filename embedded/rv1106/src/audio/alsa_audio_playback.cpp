#include "rootlink/audio/alsa_audio_playback.h"

#include <alsa/asoundlib.h>

#include <string>
#include <chrono>
#include <cerrno>
#include <thread>
#include <utility>

namespace rootlink::audio {
namespace {

Status alsaError(AudioError code, const std::string& operation, int error) {
  return {code, operation + ": " + snd_strerror(error)};
}

Status configurePcm(snd_pcm_t* pcm, const AudioConfig& config) {
  // ALSA 允许驱动返回“最接近”的 rate/period；Phase 1 不接受重采样或非 20 ms 周期。
  snd_pcm_hw_params_t* params = nullptr;
  snd_pcm_hw_params_alloca(&params);
  int rc = snd_pcm_hw_params_any(pcm, params);
  if (rc < 0) return alsaError(AudioError::kDeviceError, "cannot initialize playback parameters", rc);
  rc = snd_pcm_hw_params_set_access(pcm, params, SND_PCM_ACCESS_RW_INTERLEAVED);
  if (rc < 0) return alsaError(AudioError::kUnsupportedFormat, "cannot select interleaved playback", rc);
  rc = snd_pcm_hw_params_set_format(pcm, params, SND_PCM_FORMAT_S16_LE);
  if (rc < 0) return alsaError(AudioError::kUnsupportedFormat, "cannot select S16_LE playback", rc);
  rc = snd_pcm_hw_params_set_channels(pcm, params, config.channels);
  if (rc < 0) return alsaError(AudioError::kUnsupportedFormat, "cannot select mono playback", rc);
  unsigned int rate = config.sample_rate;
  int direction = 0;
  rc = snd_pcm_hw_params_set_rate_near(pcm, params, &rate, &direction);
  if (rc < 0 || rate != config.sample_rate) {
    return {AudioError::kUnsupportedFormat, "playback device cannot provide exactly 16000 Hz"};
  }
  snd_pcm_uframes_t period = config.samplesPerFrame();
  direction = 0;
  rc = snd_pcm_hw_params_set_period_size_near(pcm, params, &period, &direction);
  if (rc < 0 || period != config.samplesPerFrame()) {
    return {AudioError::kUnsupportedFormat, "playback device cannot provide exactly 20 ms periods"};
  }
  snd_pcm_uframes_t buffer_size = period * 4;
  rc = snd_pcm_hw_params_set_buffer_size_near(pcm, params, &buffer_size);
  if (rc < 0) return alsaError(AudioError::kDeviceError, "cannot set playback buffer size", rc);
  rc = snd_pcm_hw_params(pcm, params);
  if (rc < 0) return alsaError(AudioError::kUnsupportedFormat, "cannot apply playback parameters", rc);

  snd_pcm_format_t actual_format = SND_PCM_FORMAT_UNKNOWN;
  unsigned int actual_channels = 0, actual_rate = 0;
  snd_pcm_uframes_t actual_period = 0;
  snd_pcm_hw_params_get_format(params, &actual_format);
  snd_pcm_hw_params_get_channels(params, &actual_channels);
  direction = 0;
  snd_pcm_hw_params_get_rate(params, &actual_rate, &direction);
  direction = 0;
  snd_pcm_hw_params_get_period_size(params, &actual_period, &direction);
  if (actual_format != SND_PCM_FORMAT_S16_LE || actual_channels != 1 || actual_rate != 16000 ||
      actual_period != config.samplesPerFrame()) {
    return {AudioError::kUnsupportedFormat,
            "playback negotiation did not preserve 16000 Hz / mono / S16_LE / 20 ms"};
  }
  rc = snd_pcm_prepare(pcm);
  if (rc < 0) return alsaError(AudioError::kDeviceError, "cannot prepare playback device", rc);
  return Status::okStatus();
}

}  // namespace

struct AlsaAudioPlayback::Impl {
  snd_pcm_t* pcm{nullptr};
};

AlsaAudioPlayback::AlsaAudioPlayback(AudioConfig config)
    : config_(std::move(config)), impl_(std::make_unique<Impl>()) {}

AlsaAudioPlayback::~AlsaAudioPlayback() { (void)stop(); }

Status AlsaAudioPlayback::start() {
  if (running_.load()) return Status::okStatus();
  const Status valid = config_.validate();
  if (!valid.ok()) return valid;
  // SDK 旧版 ALSA 不提供 EINTR 选项，仍通过非阻塞写入和有界等待保证退出机会。
  int open_mode = SND_PCM_NONBLOCK;
#ifdef SND_PCM_EINTR
  open_mode |= SND_PCM_EINTR;
#endif
  int rc = snd_pcm_open(&impl_->pcm, config_.device.c_str(), SND_PCM_STREAM_PLAYBACK,
                        open_mode);
  if (rc < 0) {
    impl_->pcm = nullptr;
    return alsaError(AudioError::kDeviceError, "cannot open playback device '" + config_.device + "'", rc);
  }
  const Status configured = configurePcm(impl_->pcm, config_);
  if (!configured.ok()) {
    snd_pcm_close(impl_->pcm);
    impl_->pcm = nullptr;
    return configured;
  }
  // 与采集侧一致，统计跨多轮 start/stop 累计，供长时间板端验收使用。
  running_.store(true);
  return Status::okStatus();
}

Status AlsaAudioPlayback::writeFrame(const std::vector<std::int16_t>& frame) {
  if (!running_.load() || impl_->pcm == nullptr) {
    return {AudioError::kInvalidState, "playback device is not running"};
  }
  if (frame.size() != config_.samplesPerFrame()) {
    return {AudioError::kInvalidArgument, "playback frame must contain exactly 320 samples"};
  }
  std::size_t offset = 0;
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (offset < frame.size()) {
    if (std::chrono::steady_clock::now() >= deadline)
      return {AudioError::kTimeout, "playback device did not accept a frame within 2 seconds"};
    // 声卡短写并不等于丢帧：继续提交本帧剩余采样，直到完整 320 samples。
    const snd_pcm_sframes_t written =
        snd_pcm_writei(impl_->pcm, frame.data() + offset, frame.size() - offset);
    if (written == -EINTR) return {AudioError::kInterrupted, "playback interrupted"};
    if (written == -EAGAIN || written == 0) {
      // 有界阻塞等待而非空转；非阻塞 writei 不会在 wait 返回后再次无限等待。
      const int ready = snd_pcm_wait(impl_->pcm, 100);
      if (ready == -EINTR) return {AudioError::kInterrupted, "playback interrupted"};
      if (ready < 0) {
        const int recovered = ready == -ESTRPIPE ? snd_pcm_prepare(impl_->pcm)
                                                 : snd_pcm_recover(impl_->pcm, ready, 1);
        if (recovered < 0) return alsaError(AudioError::kDeviceError, "playback wait failed", recovered);
        ++recoveries_;
      }
      continue;
    }
    if (written < 0) {
      const int rc = written == -ESTRPIPE ? snd_pcm_prepare(impl_->pcm)
                                        : snd_pcm_recover(impl_->pcm, static_cast<int>(written), 1);
      if (rc < 0) return alsaError(AudioError::kDeviceError, "playback write failed", rc);
      ++recoveries_;
      continue;
    }
    offset += static_cast<std::size_t>(written);
  }
  return Status::okStatus();
}

Status AlsaAudioPlayback::drain() {
  if (!running_.load() || impl_->pcm == nullptr) return Status::okStatus();
  // 硬件队列约 80ms；允许最多 2s 的异常余量，防止驱动停滞卡死整个半双工运行时。
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  while (std::chrono::steady_clock::now() < deadline) {
    const int rc = snd_pcm_drain(impl_->pcm);
    if (rc == 0) return Status::okStatus();
    if (rc == -EINTR) return {AudioError::kInterrupted, "playback drain interrupted"};
    if (rc != -EAGAIN) return alsaError(AudioError::kDeviceError, "cannot drain playback device", rc);
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  return {AudioError::kTimeout, "playback drain timed out after 2 seconds"};
}

Status AlsaAudioPlayback::stop() {
  running_.store(false);
  if (impl_->pcm == nullptr) return Status::okStatus();
  snd_pcm_drop(impl_->pcm);
  const int rc = snd_pcm_close(impl_->pcm);
  impl_->pcm = nullptr;
  if (rc < 0) return alsaError(AudioError::kDeviceError, "cannot close playback device", rc);
  return Status::okStatus();
}

bool AlsaAudioPlayback::isRunning() const noexcept { return running_.load(); }

AudioDeviceStats AlsaAudioPlayback::stats() const noexcept { return {recoveries_.load()}; }

}  // namespace rootlink::audio
