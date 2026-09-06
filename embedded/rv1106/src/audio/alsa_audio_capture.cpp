#include "rootlink/audio/alsa_audio_capture.h"

#include <alsa/asoundlib.h>

#include <algorithm>
#include <cerrno>
#include <string>
#include <utility>

namespace rootlink::audio {
namespace {

Status alsaError(AudioError code, const std::string& operation, int error) {
  return {code, operation + ": " + snd_strerror(error)};
}

Status configurePcm(snd_pcm_t* pcm, const AudioConfig& config) {
  // *_near 是 ALSA 常见协商接口，所以设置后必须读取实际值并做第二次严格校验。
  snd_pcm_hw_params_t* params = nullptr;
  snd_pcm_hw_params_alloca(&params);
  int rc = snd_pcm_hw_params_any(pcm, params);
  if (rc < 0) return alsaError(AudioError::kDeviceError, "cannot initialize capture parameters", rc);
  rc = snd_pcm_hw_params_set_access(pcm, params, SND_PCM_ACCESS_RW_INTERLEAVED);
  if (rc < 0) return alsaError(AudioError::kUnsupportedFormat, "cannot select interleaved capture", rc);
  rc = snd_pcm_hw_params_set_format(pcm, params, SND_PCM_FORMAT_S16_LE);
  if (rc < 0) return alsaError(AudioError::kUnsupportedFormat, "cannot select S16_LE capture", rc);
  rc = snd_pcm_hw_params_set_channels(pcm, params, config.channels);
  if (rc < 0) return alsaError(AudioError::kUnsupportedFormat, "cannot select mono capture", rc);

  unsigned int rate = config.sample_rate;
  int direction = 0;
  rc = snd_pcm_hw_params_set_rate_near(pcm, params, &rate, &direction);
  if (rc < 0 || rate != config.sample_rate) {
    return {AudioError::kUnsupportedFormat, "capture device cannot provide exactly 16000 Hz"};
  }
  snd_pcm_uframes_t period = config.samplesPerFrame();
  direction = 0;
  rc = snd_pcm_hw_params_set_period_size_near(pcm, params, &period, &direction);
  if (rc < 0 || period != config.samplesPerFrame()) {
    return {AudioError::kUnsupportedFormat, "capture device cannot provide exactly 20 ms periods"};
  }
  snd_pcm_uframes_t buffer_size = period * 4;
  rc = snd_pcm_hw_params_set_buffer_size_near(pcm, params, &buffer_size);
  if (rc < 0) return alsaError(AudioError::kDeviceError, "cannot set capture buffer size", rc);
  rc = snd_pcm_hw_params(pcm, params);
  if (rc < 0) return alsaError(AudioError::kUnsupportedFormat, "cannot apply capture parameters", rc);

  snd_pcm_format_t actual_format = SND_PCM_FORMAT_UNKNOWN;
  unsigned int actual_channels = 0;
  unsigned int actual_rate = 0;
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
            "capture negotiation did not preserve 16000 Hz / mono / S16_LE / 20 ms"};
  }
  rc = snd_pcm_prepare(pcm);
  if (rc < 0) return alsaError(AudioError::kDeviceError, "cannot prepare capture device", rc);
  return Status::okStatus();
}

}  // namespace

struct AlsaAudioCapture::Impl {
  snd_pcm_t* pcm{nullptr};
};

AlsaAudioCapture::AlsaAudioCapture(AudioConfig config)
    : config_(std::move(config)), impl_(std::make_unique<Impl>()) {}

AlsaAudioCapture::~AlsaAudioCapture() { (void)stop(); }

Status AlsaAudioCapture::start() {
  if (running_.load()) return Status::okStatus();
  const Status valid = config_.validate();
  if (!valid.ok()) return valid;
  // 非阻塞句柄让设备占用直接返回 EBUSY；真正的数据等待交给有截止时间的 wait。
  // 较旧的 Echo-Mate ALSA 没有 SND_PCM_EINTR；不能无条件使用主机头文件的新选项。
  // 旧版通过有界 wait 返回外层检查信号，新版额外允许 EINTR 提前结束等待。
  int open_mode = SND_PCM_NONBLOCK;
#ifdef SND_PCM_EINTR
  open_mode |= SND_PCM_EINTR;
#endif
  int rc = snd_pcm_open(&impl_->pcm, config_.device.c_str(), SND_PCM_STREAM_CAPTURE,
                        open_mode);
  if (rc < 0) {
    impl_->pcm = nullptr;
    return alsaError(AudioError::kDeviceError, "cannot open capture device '" + config_.device + "'", rc);
  }
  const Status configured = configurePcm(impl_->pcm, config_);
  if (!configured.ok()) {
    snd_pcm_close(impl_->pcm);
    impl_->pcm = nullptr;
    return configured;
  }
  // 半双工每轮都会重启设备；恢复次数按对象生命周期累计，避免清空前几轮的故障。
  running_.store(true);
  return Status::okStatus();
}

Status AlsaAudioCapture::readFrame(std::vector<std::int16_t>& frame,
                                   std::chrono::milliseconds timeout) {
  if (!running_.load() || impl_->pcm == nullptr) {
    return {AudioError::kInvalidState, "capture device is not running"};
  }
  frame.resize(config_.samplesPerFrame());
  std::size_t offset = 0;
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (offset < frame.size()) {
    // snd_pcm_readi 可能短读；使用同一总截止时间拼满 320 个采样，避免向上层泄漏半帧。
    const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(
        deadline - std::chrono::steady_clock::now());
    if (remaining.count() <= 0) return {AudioError::kTimeout, "capture timed out"};
    const int wait_ms = static_cast<int>(std::min<std::int64_t>(remaining.count(), 1000));
    if (snd_pcm_state(impl_->pcm) == SND_PCM_STATE_PREPARED) {
      const int started = snd_pcm_start(impl_->pcm);
      if (started < 0) return alsaError(AudioError::kDeviceError, "cannot start capture", started);
    }
    int rc = snd_pcm_wait(impl_->pcm, wait_ms);
    if (rc == 0) return {AudioError::kTimeout, "capture timed out"};
    if (rc == -EINTR) return {AudioError::kInterrupted, "capture interrupted"};
    if (rc < 0) {
      // recover 对挂起可能无限等待 resume；挂起时重新 prepare，丢弃旧帧而不阻塞退出。
      rc = rc == -ESTRPIPE ? snd_pcm_prepare(impl_->pcm) : snd_pcm_recover(impl_->pcm, rc, 1);
      if (rc < 0) return alsaError(AudioError::kDeviceError, "capture wait failed", rc);
      ++recoveries_;
      continue;
    }
    const snd_pcm_sframes_t got = snd_pcm_readi(impl_->pcm, frame.data() + offset,
                                                frame.size() - offset);
    if (got == -EAGAIN) continue;
    if (got == -EINTR) return {AudioError::kInterrupted, "capture interrupted"};
    if (got < 0) {
      // overrun 等瞬态错误由 ALSA 恢复；不可恢复错误保留 snd_strerror 文本上报。
      rc = got == -ESTRPIPE ? snd_pcm_prepare(impl_->pcm)
                            : snd_pcm_recover(impl_->pcm, static_cast<int>(got), 1);
      if (rc < 0) return alsaError(AudioError::kDeviceError, "capture read failed", rc);
      ++recoveries_;
      continue;
    }
    if (got == 0) continue;
    offset += static_cast<std::size_t>(got);
  }
  return Status::okStatus();
}

Status AlsaAudioCapture::stop() {
  running_.store(false);
  if (impl_->pcm == nullptr) return Status::okStatus();
  snd_pcm_drop(impl_->pcm);
  const int rc = snd_pcm_close(impl_->pcm);
  impl_->pcm = nullptr;
  if (rc < 0) return alsaError(AudioError::kDeviceError, "cannot close capture device", rc);
  return Status::okStatus();
}

bool AlsaAudioCapture::isRunning() const noexcept { return running_.load(); }

AudioDeviceStats AlsaAudioCapture::stats() const noexcept { return {recoveries_.load()}; }

}  // namespace rootlink::audio
