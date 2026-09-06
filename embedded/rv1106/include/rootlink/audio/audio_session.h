#pragma once

#include <chrono>
#include <cstddef>
#include <functional>
#include <string>

#include "rootlink/audio/audio_capture.h"
#include "rootlink/audio/audio_config.h"
#include "rootlink/audio/audio_playback.h"
#include "rootlink/audio/pcm_ring_buffer.h"
#include "rootlink/audio/status.h"

namespace rootlink::audio {

/// 由主程序提供的协作式停止条件，通常读取 SIGINT/SIGTERM 标志。
using StopRequested = std::function<bool()>;

struct AudioSessionReport {
  PcmRingBufferStats buffer;
  AudioDeviceStats capture;
  AudioDeviceStats playback;
};

/// 在指定时长内采集并写 WAV；任一错误发生后仍按 capture -> writer 顺序清理。
Status recordToWav(AudioCapture& capture, const AudioConfig& config,
                   const std::string& output_path,
                   std::chrono::milliseconds duration,
                   const StopRequested& stop_requested);

/// 校验并播放完整 WAV；自然结束会 drain，信号退出不会等待剩余设备缓存。
Status playWav(AudioPlayback& playback, const std::string& input_path,
               const StopRequested& stop_requested);

/**
 * @brief 运行实时回环。
 *
 * 采集在独立生产线程中写有界环形缓冲，调用线程负责消费和播放。任一侧失败都会
 * close 缓冲区、唤醒等待方、join 生产线程并停止两个设备。
 */
Status runLoopback(AudioCapture& capture, AudioPlayback& playback,
                   const AudioConfig& config, std::size_t buffer_frames,
                   std::chrono::milliseconds duration,
                   const StopRequested& stop_requested,
                   AudioSessionReport* report);

}  // namespace rootlink::audio
