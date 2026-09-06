#pragma once

#include <chrono>
#include <cstdint>
#include <vector>

#include "rootlink/audio/status.h"

namespace rootlink::audio {

/// 设备层统计。recoveries 表示 ALSA overrun/underrun 等瞬态故障的恢复次数。
struct AudioDeviceStats {
  std::uint64_t recoveries{0};
};

/**
 * @brief 帧级采集接口，隔离 ALSA、仿真和测试假对象。
 *
 * 生命周期约定为 start -> readFrame* -> stop。start/stop 必须幂等；析构函数必须
 * 完成兜底停止。每次成功读取必须返回 AudioConfig::samplesPerFrame() 个采样。
 */
class AudioCapture {
 public:
  virtual ~AudioCapture() = default;

  /// 打开并配置设备；已启动时再次调用应直接成功。
  virtual Status start() = 0;
  /// 等待完整一帧。超时返回 kTimeout，不应被视为设备永久故障。
  virtual Status readFrame(std::vector<std::int16_t>& frame,
                           std::chrono::milliseconds timeout) = 0;
  /// 中断等待并释放资源；未启动时调用也应成功。
  virtual Status stop() = 0;
  virtual bool isRunning() const noexcept = 0;
  virtual AudioDeviceStats stats() const noexcept = 0;
};

}  // namespace rootlink::audio
