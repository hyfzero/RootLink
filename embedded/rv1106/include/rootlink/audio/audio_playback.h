#pragma once

#include <cstdint>
#include <vector>

#include "rootlink/audio/audio_capture.h"
#include "rootlink/audio/status.h"

namespace rootlink::audio {

/**
 * @brief 帧级播放接口。
 *
 * writeFrame 只接受完整的 20 ms PCM 帧。正常文件播放结束后先 drain 再 stop；用户
 * 中断或错误路径直接 stop，以免退出时继续播放内核缓冲区中的旧声音。
 */
class AudioPlayback {
 public:
  virtual ~AudioPlayback() = default;

  virtual Status start() = 0;
  virtual Status writeFrame(const std::vector<std::int16_t>& frame) = 0;
  /// 等待已经提交给设备的音频播放完；没有待播放数据时也应成功。
  virtual Status drain() = 0;
  virtual Status stop() = 0;
  virtual bool isRunning() const noexcept = 0;
  virtual AudioDeviceStats stats() const noexcept = 0;
};

}  // namespace rootlink::audio
